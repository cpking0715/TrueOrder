"""联系人领域规则：邮箱规范化、通用邮箱判定、去重键。纯函数，零 mock。"""

from __future__ import annotations

from app.domain.contacts import (
    contact_dedup_key,
    is_generic_email,
    is_valid_email,
    normalize_email,
)


class Test邮箱规范化:
    def test_大写与首尾空格被清理(self):
        assert normalize_email("  John.Smith@Example.COM ") == "john.smith@example.com"

    def test_空输入返回None表示存NULL(self):
        assert normalize_email("") is None
        assert normalize_email("   ") is None

    def test_保留本地部分大小写差异被折叠(self):
        assert normalize_email("A@B.com") == "a@b.com"


class Test邮箱有效性:
    def test_常规邮箱合法(self):
        assert is_valid_email("john@example.com")
        assert is_valid_email("a.b+c@sub.example.co.uk")

    def test_缺用户或域或点非法(self):
        assert not is_valid_email("@example.com")
        assert not is_valid_email("john@")
        assert not is_valid_email("john@example")
        assert not is_valid_email("john@@example.com")
        assert not is_valid_email("john smith@example.com")


class Test通用邮箱判定:
    def test_常见通用前缀命中(self):
        for local in ["info", "sales", "contact", "hello", "support", "admin", "inquiry"]:
            assert is_generic_email(f"{local}@example.com"), local

    def test_大小写不敏感(self):
        assert is_generic_email("SALES@example.com")

    def test_具名邮箱不是通用邮箱(self):
        assert not is_generic_email("john.smith@example.com")
        assert not is_generic_email("purchasing.mike@example.com")

    def test_无at的串按非通用处理(self):
        assert not is_generic_email("not-an-email")


class Test去重键:
    def test_同公司同邮箱大小写不同为同键(self):
        assert contact_dedup_key(7, "A@B.com") == contact_dedup_key(7, "a@b.COM")

    def test_不同公司不同键(self):
        assert contact_dedup_key(1, "a@b.com") != contact_dedup_key(2, "a@b.com")

    def test_无邮箱不参与唯一约束(self):
        assert contact_dedup_key(1, "") is None
        assert contact_dedup_key(1, "   ") is None
