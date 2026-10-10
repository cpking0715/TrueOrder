"""联系人领域规则：邮箱规范化、有效性、通用邮箱判定、公司内去重键。纯函数。"""

from __future__ import annotations

import re

# 无人名的公共收件箱前缀：命中即 is_generic，不与具名联系人混用
GENERIC_LOCAL_PARTS = frozenset(
    {
        "info", "sales", "contact", "contacts", "hello", "support", "admin",
        "inquiry", "enquiry", "office", "mail", "team", "service", "marketing",
        "customerservice", "customerservices", "reception", "frontdesk",
    }
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(raw: str | None) -> str | None:
    """strip + 小写；空输入返回 None（存 NULL，不参与唯一约束）。"""
    if raw is None:
        return None
    text = raw.strip().lower()
    return text or None


def is_valid_email(email: str) -> bool:
    """最低限度格式校验（本地@域.后缀，无空白）：用于录入拒绝，不做真实可达性判断。"""
    return bool(_EMAIL_RE.match(email.strip()))


def is_generic_email(email: str) -> bool:
    """公共收件箱前缀（info@/sales@ 等）视为通用邮箱，界面打标签、不与具名联系人混用。"""
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return False
    local = normalized.split("@", 1)[0]
    return local in GENERIC_LOCAL_PARTS


def contact_dedup_key(company_id: int, email: str | None) -> tuple[int, str] | None:
    """公司内去重键（规范化邮箱）；无邮箱返回 None（不参与唯一约束，可多条）。"""
    normalized = normalize_email(email)
    if normalized is None:
        return None
    return company_id, normalized
