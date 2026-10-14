"""开发信处理器：send_email 任务（护栏检查 → 发送 → 状态流转）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.timeutil import utc_day_bounds
from app.domain.outreach import (
    SendRejection,
    build_unsubscribe_header,
    check_send_guards,
    compose_email_body,
)
from app.infrastructure.mail import MailSender, make_mail_sender
from app.infrastructure.orm import (
    ContactORM,
    EmailMessageORM,
    SuppressionORM,
)

log = get_logger("app.outreach")


def make_send_email_handler(
    sender: MailSender | None = None, settings: Settings | None = None
):
    """send_email 任务：检查全部护栏 → 发送 → 写 sent 状态。"""

    def handler(session: Session, payload: dict) -> None:
        from app.infrastructure.enrichment import PermanentJobError
        from app.infrastructure.jobs import QuotaDeferred

        message_id = int(payload["message_id"])
        msg = session.get(EmailMessageORM, message_id)
        if msg is None:
            raise PermanentJobError(f"邮件 {message_id} 不存在")
        if msg.status in ("sent", "suppressed"):
            return  # 幂等：已处理过不重发
        if msg.status == "sending":
            # 上次执行已进入 SMTP 阶段但没写回结果（进程崩溃/提交失败）：
            # 邮件可能已经发出，自动重发会造成重复触达 → 标 failed 交人工核对
            msg.status = "failed"
            msg.error = (
                "上次发送中断（状态停留在 sending），可能已发出；"
                "为防重复发送不自动重发，请人工核对"
            )
            session.commit()
            log.warning(
                "send_email 发现中断的 sending 状态，未重发", extra={"message_id": msg.id}
            )
            return

        cfg = settings or get_settings()
        active_sender = sender or make_mail_sender(cfg)

        # 护栏前置检查（在 worker 层面再次校验，防止绕过 API 直接入队）
        contact = session.get(ContactORM, msg.contact_id) if msg.contact_id else None
        email = contact.email if contact else ""

        suppressions = [
            {"email": s.email, "domain": s.domain}
            for s in session.scalars(select(SuppressionORM))
        ]
        recent = session.scalars(
            select(EmailMessageORM.sent_at).where(
                EmailMessageORM.status == "sent",
                EmailMessageORM.contact_id == msg.contact_id,
                EmailMessageORM.sent_at >= datetime.now(UTC)
                - timedelta(days=cfg.smtp_cooldown_days),
            )
        ).all()
        sent_today = int(
            session.scalar(
                select(func.count()).select_from(EmailMessageORM).where(
                    EmailMessageORM.status == "sent",
                    EmailMessageORM.sent_at >= utc_day_bounds()[0],
                    EmailMessageORM.sent_at < utc_day_bounds()[1],
                )
            ) or 0
        )

        rejection = check_send_guards(
            company_address=cfg.company_address,
            reply_to=cfg.smtp_reply_to,
            email=email,
            do_not_contact=bool(contact.do_not_contact) if contact else True,
            verify_status=contact.verify_status if contact else "unknown",
            source=contact.source if contact else "",
            source_ref=contact.source_ref if contact else "",
            suppressions=suppressions,
            recent_sends=list(recent),
            sent_today=sent_today,
            daily_cap=cfg.smtp_daily_cap,
            cooldown_days=cfg.smtp_cooldown_days,
        )
        if rejection is not None:
            if rejection.reason is SendRejection.QUOTA:
                # 额度用尽不是失败：邮件保持 queued，任务延期到下一个 UTC 自然日
                raise QuotaDeferred(utc_day_bounds()[1], rejection.message)
            msg.status = (
                "suppressed"
                if rejection.reason in (SendRejection.SUPPRESSED, SendRejection.DO_NOT_CONTACT)
                else "failed"
            )
            msg.error = rejection.message
            session.commit()
            log.info(
                "send_email 被护栏拒绝",
                extra={"message_id": msg.id, "reason": rejection.reason.value},
            )
            return

        # 先落 sending 再调 SMTP：SMTP 成功但写回失败时，重入看到 sending 不会重发
        msg.status = "sending"
        msg.attempts += 1
        session.commit()
        body_with_footer = compose_email_body(msg.body, cfg.company_address)
        try:
            message_header = active_sender.send(
                to=email,
                subject=msg.subject,
                body=body_with_footer,
                reply_to=cfg.smtp_reply_to,
                unsubscribe_header=build_unsubscribe_header(cfg.smtp_reply_to),
            )
        except Exception as exc:
            # SMTP 明确报错（连接/认证/拒收）：视为未发出，标 failed 并抛出交给队列退避重试
            msg.status = "failed"
            msg.error = f"{type(exc).__name__}: {exc}"
            session.commit()
            log.warning("send_email SMTP 失败，将重试", extra={"message_id": msg.id}, exc_info=True)
            raise
        msg.status = "sent"
        msg.sent_at = datetime.now(UTC)
        msg.message_id_header = message_header
        msg.error = None
        session.commit()

    return handler
