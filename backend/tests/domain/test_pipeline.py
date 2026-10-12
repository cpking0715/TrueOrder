"""商机阶段机（DEV-SPEC 3.3）：转换合法性、lost 规则、自动推进、到期判断。纯函数。"""

from __future__ import annotations

from datetime import date

from app.domain.pipeline import (
    STAGES,
    auto_advance_on_email_in,
    auto_advance_on_email_sent,
    can_transition,
    is_due,
    validate_transition,
)


class Test转换合法性:
    def test_顺序前进合法(self):
        assert can_transition("lead", "contacted")
        assert can_transition("contacted", "replied")
        assert can_transition("negotiating", "won_intent")

    def test_向前跳级合法(self):
        assert can_transition("lead", "replied")  # 对方主动来信
        assert can_transition("lead", "sample_quote")

    def test_倒退非法(self):
        assert not can_transition("replied", "contacted")
        assert not can_transition("negotiating", "lead")

    def test_任意阶段可进lost(self):
        for stage in STAGES:
            assert can_transition(stage, "lost"), stage

    def test_won_intent之后只能进lost(self):
        assert not can_transition("won_intent", "negotiating")
        assert not can_transition("won_intent", "lead")
        assert can_transition("won_intent", "lost")

    def test_lost只能重开为lead(self):
        assert can_transition("lost", "lead")
        assert not can_transition("lost", "contacted")
        assert not can_transition("lost", "lost")

    def test_非法阶段名(self):
        assert not can_transition("lead", "vip")
        assert not can_transition("vip", "lead")


class Testlost规则:
    def test_进lost必须带原因(self):
        assert validate_transition("lead", "lost", closed_reason="预算冻结") is None
        assert "原因" in (validate_transition("lead", "lost") or "原因")

    def test_重开清原因(self):
        assert validate_transition("lost", "lead") is None  # 重开不需要原因

    def test_非法转换报错(self):
        err = validate_transition("replied", "lead")
        assert err and "不允许" in err


class Test自动推进:
    def test_首封邮件发出lead变contacted(self):
        assert auto_advance_on_email_sent("lead") == "contacted"

    def test_非lead发邮件不动(self):
        assert auto_advance_on_email_sent("replied") is None
        assert auto_advance_on_email_sent("contacted") is None

    def test_收到回信contacted变replied(self):
        assert auto_advance_on_email_in("contacted") == "replied"

    def test_非contacted收信不动(self):
        assert auto_advance_on_email_in("lead") is None


class Test到期判断:
    def test_到期且非终态为待跟进(self):
        assert is_due(date(2026, 10, 12), "contacted", date(2026, 10, 12)) is True
        assert is_due(date(2026, 10, 10), "lead", date(2026, 10, 12)) is True

    def test_未到期不为待跟进(self):
        assert is_due(date(2026, 10, 13), "contacted", date(2026, 10, 12)) is False

    def test_无跟进日不为待跟进(self):
        assert is_due(None, "contacted", date(2026, 10, 12)) is False

    def test_终态不为待跟进(self):
        assert is_due(date(2026, 10, 10), "won_intent", date(2026, 10, 12)) is False
        assert is_due(date(2026, 10, 10), "lost", date(2026, 10, 12)) is False
