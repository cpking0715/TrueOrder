"""AI 买家发现处理器：多角度批量生成 → 入库 → 批量排补全任务。

一次触发跑 5 个搜索角度（产品/行业/渠道/规模/区域），合并去重后 50-100 家。
全程零人工：填品名 → 点按钮 → 等 worker → 拿名单。
"""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.discover import parse_discover_response
from app.domain.entities import DiscoveredBuyer
from app.domain.normalize import normalize_company_name, normalize_country
from app.infrastructure.jobs import SqlJobQueue
from app.infrastructure.orm import CompanyORM

# 五个搜索角度：每个生成 ~20 家，合并去重后 50-100 家
DISCOVER_ANGLES = [
    "major importers and large buyers",
    "mid-size wholesale distributors and regional dealers",
    "specialty, niche, and private-label buyers",
    "department store chains and retail buying offices",
    "import agents, trading companies, and sourcing offices",
]

_ANGLE_PROMPT = (
    "List 20 real, verifiable companies that match: {angle} "
    "for the following product in the United States. "
    "Only include companies you are confident exist. "
    "Output a JSON array:\n"
    '{{"company_name": "legal name", "city": "city", '
    '"state": "2-letter code", "note": "reason"}}\n'
    "Rules:\n"
    "- Real companies only\n"
    "- Avoid retail giants (Walmart/Target/Costco)\n"
    "- Output ONLY the JSON array\n"
    "Product: {category} (HS: {hs_code})"
)


def _call_one_angle(
    angle: str, category: str, hs_code: str, settings: Settings
) -> list[DiscoveredBuyer]:
    prompt = _ANGLE_PROMPT.format(angle=angle, category=category, hs_code=hs_code)
    response = httpx.post(
        f"{settings.ai_base_url.rstrip('/')}/chat/completions",
        json={
            "model": settings.ai_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "max_tokens": 10000,
        },
        headers={"Authorization": f"Bearer {settings.ai_api_key}"},
        timeout=90,
    )
    response.raise_for_status()
    content = (
        response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    )
    return parse_discover_response(content)


def batch_discover(
    category: str, hs_code: str, settings: Settings
) -> list[DiscoveredBuyer]:
    """五角度并行生成 + 按规范化名称去重。"""
    all_buyers: list[DiscoveredBuyer] = []
    seen: set[str] = set()
    for angle in DISCOVER_ANGLES:
        try:
            buyers = _call_one_angle(angle, category, hs_code, settings)
        except Exception:  # noqa: BLE001 - 单角度失败不影响其他
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
        buyers = batch_discover(category, hs_code, cfg)

        queue = SqlJobQueue(session)
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
            queue.enqueue("find_contacts", {"company_id": company.id})

        session.commit()

    return handler
