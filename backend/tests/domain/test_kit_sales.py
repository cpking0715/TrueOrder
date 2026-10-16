"""出海包领域规则：草稿生成（fake/兜底）、跟进日、询盘状态流、PI 计算（零 mock）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.kit_sales import (
    DraftContext,
    DraftText,
    QuoteLine,
    follow_up_dates,
    generate_draft,
    line_total,
    pi_number,
    quote_total,
    validate_inquiry_transition,
    validate_quote,
)
from app.domain.outreach import UNSUBSCRIBE_LINE


def _ctx(channel: str = "email") -> DraftContext:
    return DraftContext(
        channel=channel, company="Tiny Steps LLC", country="US", contact_name="Amy",
        product="Organic Baby Romper", specs="100% cotton", moq=300, lead_time_days=30,
        selling_points=("GOTS organic",), sender_name="Lily",
    )


class FakeWriter:
    def __init__(self, text: DraftText | None = None, fail: bool = False) -> None:
        self.text, self.fail, self.calls = text, fail, 0

    def write(self, ctx: DraftContext) -> DraftText:
        self.calls += 1
        if self.fail:
            raise RuntimeError("AI 挂了")
        assert self.text is not None
        return self.text


def test_无写手走模板_邮件带主题与退订():
    draft, source = generate_draft(_ctx(), None)
    assert source == "template"
    assert draft.subject == "Organic Baby Romper for Tiny Steps LLC"
    assert "MOQ: 300" in draft.body and "Hi Amy" in draft.body
    assert draft.body.endswith(UNSUBSCRIBE_LINE)


def test_写手成功用其结果_邮件仍补退订():
    writer = FakeWriter(DraftText("Hello", "Custom body"))
    draft, source = generate_draft(_ctx(), writer)
    assert source == "llm" and draft.subject == "Hello"
    assert draft.body == "Custom body" + UNSUBSCRIBE_LINE


def test_写手失败或空内容回落模板():
    assert generate_draft(_ctx(), FakeWriter(fail=True))[1] == "template"
    assert generate_draft(_ctx(), FakeWriter(DraftText("s", "  ")))[1] == "template"


def test_WhatsApp_无主题无退订行():
    draft, _ = generate_draft(_ctx("whatsapp"), None)
    assert draft.subject == "" and UNSUBSCRIBE_LINE not in draft.body
    assert "MOQ 300" in draft.body


def test_未知渠道拒绝():
    with pytest.raises(ValueError):
        generate_draft(_ctx("sms"), None)


def test_跟进日_第3天和第7天():
    assert follow_up_dates(date(2026, 10, 16)) == (date(2026, 10, 19), date(2026, 10, 23))


@pytest.mark.parametrize(
    ("src", "dst", "ok"),
    [
        ("new", "quoted", True), ("new", "won", False), ("quoted", "sample", True),
        ("sample", "won", True), ("won", "lost", False), ("lost", "new", True),
        ("new", "unknown", False), ("quoted", "lost", True),
    ],
)
def test_询盘状态流(src, dst, ok):
    assert (validate_inquiry_transition(src, dst) is None) is ok


def test_报价校验与金额():
    assert validate_quote(1, Decimal("1.5"), "USD") == []
    assert len(validate_quote(0, Decimal("0"), "US")) == 3
    lines = [QuoteLine("A", 3, Decimal("1.005")), QuoteLine("B", 2, Decimal("2.50"))]
    assert line_total(lines[0]) == Decimal("3.02")
    assert quote_total(lines) == Decimal("8.02")
    assert pi_number(7, date(2026, 10, 16)) == "PI-20261016-0007"
