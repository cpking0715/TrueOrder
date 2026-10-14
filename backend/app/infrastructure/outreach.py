"""开发信处理器：send_email 任务（护栏检查 → 发送 → 状态流转）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.timeutil import utc_day_bounds
from app.domain.outreach import (
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
            suppressions=suppressions,
            recent_sends=list(recent),
            sent_today=sent_today,
            daily_cap=cfg.smtp_daily_cap,
            cooldown_days=cfg.smtp_cooldown_days,
        )
        if rejection:
            msg.status = "suppressed" if "抑制" in rejection else "failed"
            msg.error = rejection
            session.commit()
            if "额度" in rejection:
                raise QuotaDeferred(
                    datetime.now(UTC) + timedelta(days=1),
                    f"发送额度用完，延期至明日：{rejection}",
                )
            return

        # 发送
        body_with_unsub = compose_email_body(msg.body, cfg.company_address)
        try:
            message_header = active_sender.send(
                to=email,
                subject=msg.subject,
                body=body_with_unsub,
                reply_to=cfg.smtp_reply_to,
                unsubscribe_header=build_unsubscribe_header(cfg.smtp_reply_to),
            )
            msg.status = "sent"
            msg.sent_at = datetime.now(UTC)
            msg.message_id_header = message_header
        except Exception as exc:  # noqa: BLE001
            msg.status = "failed"
            msg.error = f"{type(exc).__name__}: {exc}"
            msg.attempts += 1
        session.commit()

    return handler
