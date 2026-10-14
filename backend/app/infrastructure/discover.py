"""AI 买家发现处理器：多角度批量生成 → 入库 → 批量排补全任务。

一次触发跑 5 个搜索角度（产品/行业/渠道/规模/区域），合并去重后 50-100 家。
全程零人工：填品名 → 点按钮 → 等 worker → 拿名单。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domain.discover import parse_discover_response
from app.domain.entities import DiscoveredBuyer
from app.domain.normalize import normalize_company_name, normalize_country
from app.infrastructure.jobs import SqlJobQueue
from app.infrastructure.llm_client import AiQuota, LlmClient
from app.infrastructure.orm import CompanyLeadSourceORM, CompanyORM

log = get_logger("app.discover")


def _record_lead(session: Session, product_id: object, company_id: int, source_ref: str) -> None:
    """记录「AI 发现」线索（产品×企业唯一，重复发现幂等）。无 product_id 的旧任务跳过。"""
    if not product_id:
        return
    session.execute(
        pg_insert(CompanyLeadSourceORM)
        .values(
            product_id=int(str(product_id)),
            company_id=company_id,
            source="ai_discover",
            source_ref=source_ref,
        )
        .on_conflict_do_nothing(constraint="uq_lead_source")
    )

# 意向线索角度：不限进口商/分销商；个人工作室、小买家、感兴趣对象都算潜在触达对象
DISCOVER_ANGLES = [
    "major importers and large wholesale buyers",
    "mid-size distributors, dealers, and specialty retailers",
    "small businesses, boutiques, and independent shops that buy or resell this product",
    "individual professionals, studios, designers, or consultants who might purchase",
    "online sellers, private-label brands, and niche end customers likely interested",
]

_ANGLE_PROMPT = (
    "List 20 real, verifiable entities that match: {angle} "
    "for the following product in the United States. "
    "Include companies AND named individuals / sole proprietors when they fit. "
    "Only include entries you are confident exist. "
    "Output a JSON array:\n"
    '{{"company_name": "legal or personal name", "city": "city", '
    '"state": "2-letter code", "note": "why they might buy or be interested"}}\n'
    "Rules:\n"
    "- Real entities only (companies or individuals)\n"
    "- Potential interest counts — not only importers/distributors\n"
    "- Avoid retail giants (Walmart/Target/Costco)\n"
    "- Output ONLY the JSON array\n"
    "Product: {category} (HS: {hs_code})"
)



def _call_one_angle(
    angle: str, category: str, hs_code: str, settings: Settings
) -> list[DiscoveredBuyer]:
    prompt = _ANGLE_PROMPT.format(angle=angle, category=category, hs_code=hs_code)
    content = LlmClient.from_settings(settings, timeout=90).chat(
        [{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=10000,
        disable_thinking=False,  # 名单生成保留推理（与原行为一致）
    )
    return parse_discover_response(content)


def batch_discover(
    category: str, hs_code: str, settings: Settings, quota: AiQuota | None = None
) -> list[DiscoveredBuyer]:
    """五角度逐个生成 + 按规范化名称去重；传 quota 时每角度计 1 次 AI 调用，额度用尽即停。"""
    all_buyers: list[DiscoveredBuyer] = []
    seen: set[str] = set()
    for angle in DISCOVER_ANGLES:
        if quota is not None:
            if quota.remaining() <= 0:
                log.warning("AI 日额度用尽，买家发现提前结束", extra={"angle": angle})
                break
            quota.record("ai-discover")
        try:
            buyers = _call_one_angle(angle, category, hs_code, settings)
        except Exception:  # noqa: BLE001 - 单角度失败不影响其他
            log.warning("买家发现单角度失败，跳过", extra={"angle": angle}, exc_info=True)
            continue
        for b in buyers:
            key = normalize_company_name(b.company_name)
            if key and key not in seen:
                seen.add(key)
                all_buyers.append(b)
    return all_buyers


def make_discover_buyers_handler(settings: Settings | None = None):
    """对产品触发 AI 买家发现：五角度生成 → 入库 → 批量排补全任务。"""

    def handler(session: Session, payload: dict) -> None:
        from app.infrastructure.enrichment import PermanentJobError

        category = str(payload.get("category") or "").strip()
        if not category:
            raise PermanentJobError("品类描述不能为空")

        cfg = settings or get_settings()
        if not cfg.ai_api_key:
            raise PermanentJobError("未配置 AI Key，无法自动发现买家")

        hs_code = str(payload.get("hs_code") or "").strip()
        quota = AiQuota(session, cfg.ai_daily_cap)
        if quota.remaining() <= 0:
            from app.core.timeutil import utc_day_bounds
            from app.infrastructure.jobs import QuotaDeferred

            raise QuotaDeferred(utc_day_bounds()[1], "今日 AI 调用额度已用尽")
        buyers = batch_discover(category, hs_code, cfg, quota=quota)

        queue = SqlJobQueue(session)
        product_id = payload.get("product_id")
        source_ref = f"discover_buyers:{category[:200]}"
        for buyer in buyers:
            normalized = normalize_company_name(buyer.company_name)
            country = normalize_country(buyer.country) or "US"
            existing = session.scalar(
                select(CompanyORM.id).where(
                    CompanyORM.normalized_name == normalized,
                    CompanyORM.country == country,
                )
            )
            if existing:
                # 已在库的企业不重复建/补全，但仍记为本产品的发现线索
                _record_lead(session, product_id, existing, source_ref)
                continue
            company = CompanyORM(
                normalized_name=normalized,
                country=country,
                name_variants=[buyer.company_name],
                city_guess=buyer.city or "",
                address_guess="",
            )
            session.add(company)
            session.flush()
            _record_lead(session, product_id, company.id, source_ref)
            queue.enqueue(
                "find_contacts",
                {"company_id": company.id, **({"product_id": product_id} if product_id else {})},
            )

        session.commit()
        if product_id:
            # 让发现的企业立即以 SOURCE_LEAD 出现在该产品潜在层（不必等下一次全量重打分）
            from app.infrastructure.importers import CsvImporter

            CsvImporter(session).rescore_one(int(product_id), date.today())

    return handler
