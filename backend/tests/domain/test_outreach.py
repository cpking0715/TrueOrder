"""开发信领域规则测试（纯函数，零 mock）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.outreach import (
    TEMPLATE_VARIABLES,
    UNSUBSCRIBE_LINE,
    build_unsubscribe_header,
    check_send_guards,
    daily_remaining,
    is_in_cooldown,
    is_suppressed,
    render_template,
    validate_template,
)


class Test模板渲染:
    def test_正常渲染(self):
        result = render_template(
            "Hello {contact_name} at {company}", {"contact_name": "John", "company": "Acme"}
        )
        assert result == "Hello John at Acme"

    def test_缺变量报错且指出变量名(self):
        with pytest.raises(ValueError, match="company"):
            render_template("Hello {contact_name} at {company}", {"contact_name": "John"})

    def test_空值视为缺失(self):
        with pytest.raises(ValueError):
            render_template("Hi {contact_name}", {"contact_name": ""})

    def test_验证模板变量名(self):
        assert validate_template("{company} and {contact_name}") == []
        assert validate_template("{company} and {unknown_var}") == ["unknown_var"]

    def test_支持的全部变量都合法(self):
        all_vars = " ".join(f"{{{v}}}" for v in TEMPLATE_VARIABLES)
        assert validate_template(all_vars) == []


class Test抑制判定:
    def test_邮箱精确匹配(self):
        assert is_suppressed("john@x.com", [{"email": "john@x.com"}]) is True

    def test_域名匹配(self):
        assert is_suppressed("any@spam.com", [{"domain": "spam.com"}]) is True

    def test_子域名也命中(self):
        assert is_suppressed("a@mail.spam.com", [{"domain": "spam.com"}]) is True

    def test_不命中(self):
        assert is_suppressed("ok@good.com", [{"email": "john@x.com"}]) is False

    def test_空邮箱直接抑制(self):
        assert is_suppressed("", []) is True


class Test冷却与额度:
    def test_三天内发过在冷却(self):
        now = datetime.now(UTC)
        recent = [now - timedelta(days=1)]
        assert is_in_cooldown("a@x.com", recent, cooldown_days=3) is True

    def test_超过三天不在冷却(self):
        now = datetime.now(UTC)
        recent = [now - timedelta(days=4)]
        assert is_in_cooldown("a@x.com", recent, cooldown_days=3) is False

    def test_日额度(self):
        assert daily_remaining(10, 30) == 20
        assert daily_remaining(30, 30) == 0
        assert daily_remaining(35, 30) == 0


class Test护栏:
    def _base(self, **over):
        params = dict(
            email="ok@x.com", do_not_contact=False, verify_status="unknown",
            suppressions=[], recent_sends=[], sent_today=0,
        )
        params.update(over)
        return params

    def test_全通过返回None(self):
        assert check_send_guards(**self._base()) is None

    def test_不再联系拒绝(self):
        assert "不再联系" in check_send_guards(**self._base(do_not_contact=True))

    def test_无效邮箱拒绝(self):
        assert "invalid" in check_send_guards(**self._base(verify_status="invalid"))

    def test_抑制名单拒绝(self):
        assert "抑制" in check_send_guards(
            **self._base(suppressions=[{"email": "ok@x.com"}]))

    def test_额度用完拒绝(self):
        assert "额度" in check_send_guards(**self._base(sent_today=30))

    def test_冷却拒绝(self):
        now = datetime.now(UTC)
        assert "冷却" in check_send_guards(
            **self._base(recent_sends=[now - timedelta(hours=12)]))


class Test退订:
    def test_Header格式(self):
        h = build_unsubscribe_header("reply@myco.com")
        assert h == "<mailto:reply@myco.com>"

    def test_正文退订语句存在(self):
        assert "STOP" in UNSUBSCRIBE_LINE
