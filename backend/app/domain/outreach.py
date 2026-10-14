"""开发信领域规则：模板渲染、抑制判定、冷却/日限护栏（纯函数）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

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
        blocked = (s.get("domain") or "").strip().lower().lstrip("@.")
        if blocked and (domain == blocked or domain.endswith("." + blocked)):
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


def missing_sender_config(company_address: str, reply_to: str) -> list[str]:
    """合规必填的发件配置缺失项（CAN-SPAM 物理地址 + 可用的退订回复地址）。"""
    missing = []
    if not company_address.strip():
        missing.append("TRUEORDER_COMPANY_ADDRESS（公司物理地址）")
    if not reply_to.strip():
        missing.append("TRUEORDER_SMTP_REPLY_TO（退订回复地址）")
    return missing


class SendRejection(StrEnum):
    """拒发原因（结构化，调用方按枚举分支，不再匹配中文文案）。"""

    SENDER_CONFIG_MISSING = "sender_config_missing"  # 缺公司地址/退订回复地址
    DO_NOT_CONTACT = "do_not_contact"
    INVALID_EMAIL = "invalid_email"  # 验证状态 invalid / bounced
    NO_SOURCE = "no_source"  # 缺来源记录（AGENTS 硬约束：只发有来源记录的联系人）
    SUPPRESSED = "suppressed"
    COOLDOWN = "cooldown"
    QUOTA = "quota"  # 今日额度用尽：可延期重试，不是失败


@dataclass(frozen=True)
class GuardRejection:
    reason: SendRejection
    message: str  # 面向用户的说明（只用于展示，不参与逻辑判断）


def has_source_record(source: str, source_ref: str) -> bool:
    """来源可追溯：source 必填；非手工录入还须有 source_ref（接口名/页面 URL/文件名）。"""
    if not (source or "").strip():
        return False
    return source == "manual" or bool((source_ref or "").strip())


def check_send_guards(
    *,
    company_address: str,
    reply_to: str,
    email: str,
    do_not_contact: bool,
    verify_status: str,
    source: str,
    source_ref: str,
    suppressions: list[dict],
    recent_sends: list[datetime],
    sent_today: int,
    daily_cap: int = 30,
    cooldown_days: int = 3,
) -> GuardRejection | None:
    """全量护栏检查；None = 可发，否则返回结构化拒发原因。

    发件配置（公司地址、退订回复地址）缺失时一律拒绝：DEV-SPEC 3.5 每封信必须带
    物理地址与可用的退订途径，不允许用占位地址兜底。
    """
    missing = missing_sender_config(company_address, reply_to)
    if missing:
        return GuardRejection(
            SendRejection.SENDER_CONFIG_MISSING, f"发件配置缺失，拒绝发送：{'、'.join(missing)}"
        )
    if do_not_contact:
        return GuardRejection(SendRejection.DO_NOT_CONTACT, "联系人已标记不再联系")
    if verify_status in ("invalid", "bounced"):
        return GuardRejection(
            SendRejection.INVALID_EMAIL, f"邮箱验证状态为 {verify_status}，不发送"
        )
    if not has_source_record(source, source_ref):
        return GuardRejection(
            SendRejection.NO_SOURCE, "联系人缺少来源记录（source/source_ref），不发送"
        )
    if is_suppressed(email, suppressions):
        return GuardRejection(SendRejection.SUPPRESSED, "命中抑制名单")
    if is_in_cooldown(email, recent_sends, cooldown_days):
        return GuardRejection(SendRejection.COOLDOWN, f"冷却中（{cooldown_days} 天内已发过）")
    if daily_remaining(sent_today, daily_cap) <= 0:
        return GuardRejection(SendRejection.QUOTA, f"今日发送额度已用完（上限 {daily_cap}）")
    return None


def build_unsubscribe_header(reply_to: str) -> str:
    """List-Unsubscribe 头（mailto 形式，本地部署无公网退订页）。

    reply_to 必填：不再用 unsubscribe@localhost 兜底（那是不可用的退订地址）。
    """
    if not reply_to.strip():
        raise ValueError("缺少退订回复地址（TRUEORDER_SMTP_REPLY_TO）")
    return f"<mailto:{reply_to.strip()}>"


def compose_email_body(body: str, company_address: str) -> str:
    """正文 + 页脚（退订语句 + 公司物理地址）。"""
    if not company_address.strip():
        raise ValueError("缺少公司物理地址（TRUEORDER_COMPANY_ADDRESS）")
    return body + UNSUBSCRIBE_LINE + "\n" + company_address.strip()
