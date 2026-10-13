"""回复识别领域规则：分类回信/退订/退信 + 自动动作判定（纯函数）。"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass


class ReplyKind(enum.StrEnum):
    REPLY = "reply"                # 正常回信（有意向或问题）
    UNSUBSCRIBE = "unsubscribe"    # 退订请求
    BOUNCE = "bounce"              # 退信（邮箱不可达）
    AUTO_REPLY = "auto_reply"      # 自动回复（out of office 等）


@dataclass(frozen=True)
class ClassifiedReply:
    kind: ReplyKind
    matched_message_id: str | None  # 关联的已发邮件 Message-ID
    sender_email: str
    subject: str
    should_advance_stage: bool
    should_suppress: bool
    should_mark_bounced: bool


# 退订关键词（正文或主题出现即判退订）
_UNSUB_PATTERNS = re.compile(
    r"unsubscribe|opt.?out|remove.?me|stop.?sending|退订|不再接收|list.?unsubscribe",
    re.IGNORECASE,
)

# 退信特征（DSN/Mailer-Daemon）
_BOUNCE_SENDERS = re.compile(r"mailer-daemon|postmaster|mail-daemon", re.IGNORECASE)
_BOUNCE_SUBJECTS = re.compile(
    r"undeliverable|delivery.?failed|delivery.?status.?notification|returned.?mail|"
    r"mail.?delivery.?failure|退信|无法送达",
    re.IGNORECASE,
)

# 自动回复特征
_AUTO_REPLY_SUBJECTS = re.compile(
    r"out.?of.?office|auto.?reply|automatic.?reply|vacation|不在办公室|自动回复",
    re.IGNORECASE,
)

# 有意向特征（用于 should_advance_stage）
_INTEREST_PATTERNS = re.compile(
    r"interested|pricing|quote|catalog|samples?|more.?info|specification|"
    r"MOQ|price.?list|interested|兴趣|报价|目录|样品",
    re.IGNORECASE,
)


def classify_reply(
    *,
    sender_email: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> ClassifiedReply:
    """分类一封收到的邮件；返回分类 + 应执行的动作。"""
    is_bounce_sender = bool(_BOUNCE_SENDERS.search(sender_email))
    is_bounce_subject = bool(_BOUNCE_SUBJECTS.search(subject))
    is_unsub = bool(_UNSUB_PATTERNS.search(subject + " " + body))
    is_auto = bool(_AUTO_REPLY_SUBJECTS.search(subject))

    # 优先级：退信 > 退订 > 自动回复 > 正常回信
    if is_bounce_sender or (is_bounce_subject and is_bounce_sender):
        return ClassifiedReply(
            kind=ReplyKind.BOUNCE,
            matched_message_id=in_reply_to or _extract_from_references(references),
            sender_email=sender_email,
            subject=subject,
            should_advance_stage=False,
            should_suppress=True,
            should_mark_bounced=True,
        )

    if is_unsub:
        return ClassifiedReply(
            kind=ReplyKind.UNSUBSCRIBE,
            matched_message_id=in_reply_to or _extract_from_references(references),
            sender_email=sender_email,
            subject=subject,
            should_advance_stage=False,
            should_suppress=True,
            should_mark_bounced=False,
        )

    if is_auto:
        return ClassifiedReply(
            kind=ReplyKind.AUTO_REPLY,
            matched_message_id=in_reply_to or _extract_from_references(references),
            sender_email=sender_email,
            subject=subject,
            should_advance_stage=False,
            should_suppress=False,
            should_mark_bounced=False,
        )

    # 正常回信：如果内容含意向词 → 推进阶段
    has_interest = bool(_INTEREST_PATTERNS.search(body))
    return ClassifiedReply(
        kind=ReplyKind.REPLY,
        matched_message_id=in_reply_to or _extract_from_references(references),
        sender_email=sender_email,
        subject=subject,
        should_advance_stage=has_interest,
        should_suppress=False,
        should_mark_bounced=False,
    )


def _extract_from_references(references: str | None) -> str | None:
    """References 头可能含多个 Message-ID，取最后一个（最近的）。"""
    if not references:
        return None
    ids = [i.strip() for i in references.split() if i.strip().startswith("<")]
    return ids[-1] if ids else None
