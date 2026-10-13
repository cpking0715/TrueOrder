"""开发信领域规则：模板渲染、抑制判定、冷却/日限护栏（纯函数）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# 模板支持的变量（渲染时缺失则报错，不输出空串）
TEMPLATE_VARIABLES = frozenset({
    "company", "contact_name", "product",
    "last_arrival", "shipments", "supplier", "sender_name",
})

_VAR_RE = re.compile(r"\{(\w+)\}")

UNSUBSCRIBE_LINE = (
    "\n\n—\nIf you no longer wish to receive these emails, "
    "reply with STOP and we will remove you from our list."
)


@dataclass(frozen=True)
class RenderResult:
    subject: str
    body: str


def validate_template(template_str: str) -> list[str]:
    """检查模板里的变量名是否都在支持列表；返回不认识的变量名。"""
    found = set(_VAR_RE.findall(template_str))
    return sorted(found - TEMPLATE_VARIABLES)


def render_template(template: str, variables: dict[str, str]) -> str:
    """渲染模板；缺失变量抛 ValueError（指出变量名），不输出空串。"""
    missing = []
    for match in _VAR_RE.finditer(template):
        name = match.group(1)
        if name not in variables or not str(variables[name]).strip():
            missing.append(name)
    if missing:
        raise ValueError(f"模板缺少变量：{', '.join(sorted(set(missing)))}")
    result = template
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def is_suppressed(email: str, suppressions: list[dict]) -> bool:
    """邮箱或域名命中任一抑制记录即 True。"""
    if not email:
        return True  # 无邮箱不发送
    email_lower = email.strip().lower()
    domain = email_lower.split("@")[-1] if "@" in email_lower else ""
    for s in suppressions:
        if s.get("email") and s["email"].strip().lower() == email_lower:
            return True
        if s.get("domain") and domain.endswith(s["domain"].strip().lower()):
            return True
    return False


def is_in_cooldown(
    email: str, recent_sends: list[datetime], cooldown_days: int = 3,
) -> bool:
    """同一联系人 N 天内已发过信 → True（防重复触达）。"""
    if not email or not recent_sends:
        return False
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=cooldown_days)
    return any(s >= cutoff for s in recent_sends)


def daily_remaining(sent_today: int, daily_cap: int = 30) -> int:
    """今日剩余可发额度。"""
    return max(daily_cap - sent_today, 0)


def check_send_guards(
    *,
    email: str,
    do_not_contact: bool,
    verify_status: str,
    suppressions: list[dict],
    recent_sends: list[datetime],
    sent_today: int,
    daily_cap: int = 30,
    cooldown_days: int = 3,
) -> str | None:
    """全量护栏检查；返回 None=可发，否则返回拒绝原因（状态码用）。"""
    if do_not_contact:
        return "联系人已标记不再联系"
    if verify_status in ("invalid", "bounced"):
        return f"邮箱验证状态为 {verify_status}，不发送"
    if is_suppressed(email, suppressions):
        return "命中抑制名单"
    if is_in_cooldown(email, recent_sends, cooldown_days):
        return f"冷却中（{cooldown_days} 天内已发过）"
    if daily_remaining(sent_today, daily_cap) <= 0:
        return f"今日发送额度已用完（上限 {daily_cap}）"
    return None


def build_unsubscribe_header(reply_to: str = "") -> str:
    """List-Unsubscribe 头（mailto 形式，本地部署无公网退订页）。"""
    return f"<mailto:{reply_to or 'unsubscribe@localhost'}>"
