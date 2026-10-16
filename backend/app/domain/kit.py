"""出海包 v0.1（内部工具）领域规则：14 天任务、产品档案校验、买家行清洗。纯函数。

定位不变：自家企业内部用，单用户；不对外售卖名单、不自动发信。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.domain.contacts import is_valid_email, normalize_email
from app.domain.normalize import normalize_company_name, normalize_country

# 页面键：任务条目据此跳转到对应页面；external 表示站外操作（手册里给链接）
KIT_PAGES = ("today", "products", "buyers", "drafts", "inquiries", "external")


@dataclass(frozen=True)
class KitTask:
    key: str
    day: int
    title: str
    page: str


KIT_TASKS: tuple[KitTask, ...] = (
    KitTask("d1_buyer_type", 1, "确定只卖给哪类买家（零售/批发/品牌）", "today"),
    KitTask("d2_pick_products", 2, "选 3 个主推款并录入产品档案", "products"),
    KitTask("d2_pitch", 2, "为每个主推款写一句话卖点", "products"),
    KitTask("d3_storefront", 3, "准备英文公司名与 WhatsApp 商务号", "external"),
    KitTask("d4_specs", 4, "补齐尺码/面料/MOQ/交期等规格", "products"),
    KitTask("d5_market", 5, "选定一个目标市场（美/欧/中东其一）", "buyers"),
    KitTask("d6_import", 6, "导入 50–100 个买家线索并去重", "buyers"),
    KitTask("d7_tag", 7, "给线索打国家/渠道/阶段标签", "buyers"),
    KitTask("d8_first_draft", 8, "生成第一封开发信草稿（只生成不发送）", "drafts"),
    KitTask("d9_follow_up", 9, "按第 3 天/第 7 天提醒准备跟进稿", "drafts"),
    KitTask("d10_inquiry", 10, "登记收到的询盘并分级", "inquiries"),
    KitTask("d11_quote", 11, "给询盘出报价并导出 PI", "inquiries"),
    KitTask("d12_sample", 12, "跟进样品：运费、寄样、追踪", "inquiries"),
    KitTask("d13_payment", 13, "对照收款方式与发货检查表", "external"),
    KitTask("d14_review", 14, "复盘：发出数、回复率、下一轮名单", "today"),
)
KIT_DAYS = 14
TASK_KEYS = frozenset(t.key for t in KIT_TASKS)


def current_day(done: Mapping[str, bool]) -> int:
    """「今天」= 最早还有未完成任务的那一天（自定节奏，不按日历硬推）；全完成停在第 14 天。"""
    for task in KIT_TASKS:
        if not done.get(task.key, False):
            return task.day
    return KIT_DAYS


def tasks_for_day(day: int) -> list[KitTask]:
    return [t for t in KIT_TASKS if t.day == day]


# ---------- 产品档案 ----------

FEATURED_LIMIT = 5
_URL_RE = re.compile(r"^https?://[^\s]+$")


@dataclass(frozen=True)
class ProductProfileInput:
    image_url: str
    specs: str
    moq: int
    lead_time_days: int
    selling_points: tuple[str, ...]
    featured: bool


def validate_profile(p: ProductProfileInput) -> list[str]:
    """返回错误列表（空 = 合法）。图片只收 http(s) 链接，不收上传。"""
    errors: list[str] = []
    if p.image_url and not _URL_RE.match(p.image_url.strip()):
        errors.append("图片地址必须是 http(s) 链接")
    if p.moq < 1:
        errors.append("MOQ 必须 ≥ 1")
    if not 1 <= p.lead_time_days <= 365:
        errors.append("交期必须在 1–365 天之间")
    points = [s for s in p.selling_points if s.strip()]
    if len(points) > 5:
        errors.append("卖点最多 5 条")
    return errors


def can_feature(currently_featured: int, already_featured: bool) -> bool:
    """主推款上限 5 个；已是主推的再次保存不占新名额。"""
    return already_featured or currently_featured < FEATURED_LIMIT


# ---------- 买家线索 ----------

BUYER_STAGES = ("new", "contacted", "replied", "inquiry")
BUYER_CHANNELS = ("email", "whatsapp", "linkedin", "trade_show", "website", "other")


@dataclass(frozen=True)
class BuyerRow:
    company_name: str
    country: str
    contact_name: str
    email: str | None
    phone: str
    channel: str
    stage: str


@dataclass
class BuyerRowsResult:
    valid: list[BuyerRow] = field(default_factory=list)
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)


def _norm_choice(raw: str, choices: tuple[str, ...], default: str) -> str | None:
    value = (raw or "").strip().lower().replace(" ", "_") or default
    return value if value in choices else None


def clean_buyer_rows(rows: Iterable[Mapping[str, str | None]]) -> BuyerRowsResult:
    """CSV 行 → 合法买家；文件内去重（邮箱优先，无邮箱按 规范化名+国家）。

    行号从 2 起（第 1 行是表头）。邮箱可空，但填了就必须格式合法。
    """
    result = BuyerRowsResult()
    seen: set[str] = set()
    for row_no, row in enumerate(rows, start=2):
        name = (row.get("company_name") or "").strip()
        if not normalize_company_name(name):
            result.errors.append(f"第 {row_no} 行：缺少企业名")
            continue
        country = normalize_country((row.get("country") or "").strip())
        if len(country) != 2:
            result.errors.append(f"第 {row_no} 行：缺少或无法识别国家")
            continue
        email = normalize_email(row.get("email"))
        if email is not None and not is_valid_email(email):
            result.errors.append(f"第 {row_no} 行：邮箱格式非法 {row.get('email')!r}")
            continue
        channel = _norm_choice(row.get("channel") or "", BUYER_CHANNELS, "email")
        stage = _norm_choice(row.get("stage") or "", BUYER_STAGES, "new")
        if channel is None or stage is None:
            result.errors.append(f"第 {row_no} 行：渠道或阶段取值不认识")
            continue
        key = email or f"{normalize_company_name(name)}\x00{country}"
        if key in seen:
            result.duplicates += 1
            continue
        seen.add(key)
        result.valid.append(
            BuyerRow(
                company_name=name,
                country=country,
                contact_name=(row.get("contact_name") or "").strip(),
                email=email,
                phone=(row.get("phone") or "").strip(),
                channel=channel,
                stage=stage,
            )
        )
    return result
