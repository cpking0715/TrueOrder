"""IMAP 回复识别处理器：轮询收件箱 → 分类 → 自动动作（阶段/抑制/退信标记）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.reply_detection import ReplyKind, classify_reply
from app.infrastructure.orm import (
    ActivityORM,
    ContactORM,
    EmailMessageORM,
    OpportunityORM,
    SuppressionORM,
)


class FakeImapInbox:
    """测试用 IMAP 收件箱（注入预置邮件）。"""

    def __init__(self, messages: list[dict]) -> None:
        self._messages = messages

    def fetch_recent(self, lookback_count: int = 20) -> list[dict]:
        return self._messages[:lookback_count]


def make_poll_imap_handler(
    inbox=None, settings: Settings | None = None
):
    """poll_imap 任务：拉收件箱 → 分类 → 按分类执行自动动作。"""

    def handler(session: Session, payload: dict) -> None:

        cfg = settings or get_settings()
        active_inbox = inbox

        if active_inbox is None:
            if not cfg.smtp_host:
                return  # 未配置 SMTP/IMAP，跳过
            active_inbox = _make_real_inbox(cfg)

        messages = active_inbox.fetch_recent()

        for msg in messages:
            result = classify_reply(
                sender_email=msg.get("sender", ""),
                subject=msg.get("subject", ""),
                body=msg.get("body", ""),
                in_reply_to=msg.get("in_reply_to"),
                references=msg.get("references"),
            )

            # 通过 Message-ID 关联已发邮件
            sent = _find_sent_by_message_id(session, result.matched_message_id)
            if sent is None:
                continue  # 无法关联到已发邮件，跳过

            contact = session.get(ContactORM, sent.contact_id) if sent.contact_id else None
            opp = session.get(OpportunityORM, sent.opportunity_id)

            # 1. 退订/退信 → 写抑制名单
            if result.should_suppress:
                existing = session.scalar(
                    select(SuppressionORM).where(
                        SuppressionORM.email == result.sender_email.lower()
                    )
                )
                if not existing:
                    reason = (
                        "unsubscribed"
                        if result.kind == ReplyKind.UNSUBSCRIBE
                        else "bounced"
                    )
                    session.add(SuppressionORM(
                        email=result.sender_email.lower(),
                        reason=reason,
                    ))

            # 2. 退信 → 联系人标 bounced
            if result.should_mark_bounced and contact:
                contact.verify_status = "bounced"

            # 3. 正常回信 → 推进阶段（contacted → replied）
            if result.should_advance_stage and opp and opp.stage == "contacted":
                session.add(ActivityORM(
                    opportunity_id=opp.id,
                    contact_id=contact.id if contact else None,
                    kind="email_in",
                    summary=f"收到回信：{result.subject[:80]}",
                ))
                opp.stage = "replied"

            # 4. 记录收到的邮件（任何类型都记活动）
            if opp:
                kind_map = {
                    ReplyKind.REPLY: "email_in",
                    ReplyKind.UNSUBSCRIBE: "note",
                    ReplyKind.BOUNCE: "note",
                    ReplyKind.AUTO_REPLY: "note",
                }
                if result.kind == ReplyKind.REPLY:
                    # email_in 已在上面推进时写了，这里避免重复
                    if not result.should_advance_stage:
                        session.add(ActivityORM(
                            opportunity_id=opp.id,
                            contact_id=contact.id if contact else None,
                            kind="email_in",
                            summary=f"收到回信：{result.subject[:80]}",
                        ))
                else:
                    session.add(ActivityORM(
                        opportunity_id=opp.id,
                        kind=kind_map.get(result.kind, "note"),
                        summary=f"[{result.kind.value}] {result.subject[:60]}",
                    ))

        session.commit()

    return handler


def _find_sent_by_message_id(session: Session, message_id: str | None):
    if not message_id:
        return None
    return session.scalar(
        select(EmailMessageORM).where(
            EmailMessageORM.message_id_header == message_id
        )
    )


def _make_real_inbox(cfg: Settings):
    """真实 IMAP 收件箱（用 imaplib 轮询）。"""
    import email
    import imaplib

    class RealInbox:
        def fetch_recent(self, count: int = 20) -> list[dict]:
            conn = imaplib.IMAP4_SSL(cfg.smtp_host.replace("smtp.", "imap."))
            conn.login(cfg.smtp_user, cfg.smtp_password)
            conn.select("INBOX")
            _, data = conn.search(None, "UNSEEN")
            ids = data[0].split()[-count:]
            results = []
            for num in ids:
                _, msg_data = conn.fetch(num, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                results.append({
                    "sender": msg.get("From", ""),
                    "subject": msg.get("Subject", ""),
                    "body": body,
                    "in_reply_to": msg.get("In-Reply-To"),
                    "references": msg.get("References"),
                })
            conn.logout()
            return results

    return RealInbox()
