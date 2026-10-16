"""出海包 v0.1 领域规则：开发信草稿（只生成不发送）、跟进提醒、询盘状态流、PI 计算。纯函数。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.domain.outreach import UNSUBSCRIBE_LINE

DRAFT_CHANNELS = ("email", "whatsapp")
FOLLOW_UP_OFFSETS = (3, 7)  # 第 3 天、第 7 天跟进


@dataclass(frozen=True)
class DraftContext:
    channel: str
    company: str
    country: str
    contact_name: str
    product: str
    specs: str
    moq: int
    lead_time_days: int
    selling_points: tuple[str, ...]
    sender_name: str


@dataclass(frozen=True)
class DraftText:
    subject: str
    body: str


class DraftWriter(Protocol):
    """开发信文案端口（LLM 实现/测试 fake 可替换）；失败抛异常，由领域兜底模板。"""

    def write(self, ctx: DraftContext) -> DraftText: ...


def follow_up_dates(generated_on: date) -> tuple[date, ...]:
    return tuple(generated_on + timedelta(days=d) for d in FOLLOW_UP_OFFSETS)


def template_draft(ctx: DraftContext) -> DraftText:
    """无 AI Key 或 AI 失败时的确定性兜底模板（英文，面向海外买家）。"""
    greeting = f"Hi {ctx.contact_name}," if ctx.contact_name else "Hello,"
    points = "; ".join(p for p in ctx.selling_points if p.strip()) or ctx.specs
    sender = ctx.sender_name or "our team"
    if ctx.channel == "whatsapp":
        body = (
            f"{greeting} this is {sender}. We make {ctx.product} for buyers in "
            f"{ctx.country}: {points}. MOQ {ctx.moq} pcs, lead time {ctx.lead_time_days} days. "
            "Can I send you our catalog?"
        )
        return DraftText(subject="", body=body)
    body = (
        f"{greeting}\n\nI noticed {ctx.company} sources kidswear and wanted to introduce "
        f"our {ctx.product}.\n\n- {points}\n- MOQ: {ctx.moq} pcs\n"
        f"- Lead time: {ctx.lead_time_days} days\n\n"
        "Would you like our catalog and price list?\n\n"
        f"Best regards,\n{sender}"
    )
    return DraftText(subject=f"{ctx.product} for {ctx.company}", body=body)


def generate_draft(ctx: DraftContext, writer: DraftWriter | None) -> tuple[DraftText, str]:
    """返回 (草稿, 来源 llm|template)。邮件一律补退订说明；WhatsApp 不加主题。"""
    if ctx.channel not in DRAFT_CHANNELS:
        raise ValueError(f"不支持的渠道：{ctx.channel}")
    draft, source = template_draft(ctx), "template"
    if writer is not None:
        try:
            got = writer.write(ctx)
            if got.body.strip():
                draft, source = got, "llm"
        except Exception:  # noqa: BLE001 - AI 任何失败都回落模板，不阻断用户
            draft, source = template_draft(ctx), "template"
    if ctx.channel == "email":
        subject = draft.subject.strip() or f"{ctx.product} for {ctx.company}"
        body = draft.body
        if UNSUBSCRIBE_LINE.strip() not in body:
            body += UNSUBSCRIBE_LINE
        return DraftText(subject=subject, body=body), source
    return DraftText(subject="", body=draft.body), source


# ---------- 询盘状态流 ----------

INQUIRY_STATUSES = ("new", "quoted", "sample", "won", "lost")
INQUIRY_LABELS = {
    "new": "新询盘",
    "quoted": "已报价",
    "sample": "等样品",
    "won": "赢单",
    "lost": "丢单",
}
_TRANSITIONS = {
    "new": {"quoted", "sample", "lost"},
    "quoted": {"sample", "won", "lost"},
    "sample": {"quoted", "won", "lost"},
    "won": set(),
    "lost": {"new"},  # 丢单可重开
}


def validate_inquiry_transition(from_status: str, to_status: str) -> str | None:
    """None = 合法；否则返回 422 文案。"""
    if to_status not in INQUIRY_STATUSES:
        return f"未知状态：{to_status}"
    if to_status not in _TRANSITIONS.get(from_status, set()):
        src = INQUIRY_LABELS.get(from_status, from_status)
        return f"不允许的状态转换：{src} → {INQUIRY_LABELS[to_status]}"
    return None


# ---------- 报价 / PI ----------

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class QuoteLine:
    description: str
    quantity: int
    unit_price: Decimal


def line_total(line: QuoteLine) -> Decimal:
    return (line.unit_price * line.quantity).quantize(_CENT, rounding=ROUND_HALF_UP)


def quote_total(lines: list[QuoteLine]) -> Decimal:
    return sum((line_total(x) for x in lines), Decimal("0.00"))


def validate_quote(quantity: int, unit_price: Decimal, currency: str) -> list[str]:
    errors: list[str] = []
    if quantity < 1:
        errors.append("数量必须 ≥ 1")
    if unit_price <= 0:
        errors.append("单价必须 > 0")
    if len(currency) != 3 or not currency.isalpha():
        errors.append("币种必须是 3 位字母（如 USD）")
    return errors


def pi_number(inquiry_id: int, issued_on: date) -> str:
    return f"PI-{issued_on:%Y%m%d}-{inquiry_id:04d}"
