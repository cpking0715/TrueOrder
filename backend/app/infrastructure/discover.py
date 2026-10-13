"""AI 买家发现处理器：DeepSeek 生成 → 入库 → 批量排补全任务。"""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.discover import build_discover_messages, parse_discover_response
from app.domain.entities import DiscoveredBuyer
from app.domain.normalize import normalize_company_name, normalize_country
from app.infrastructure.jobs import SqlJobQueue
from app.infrastructure.orm import CompanyORM


def call_deepseek_discover(
    category: str, hs_code: str, settings: Settings
) -> list[DiscoveredBuyer]:
    """调 DeepSeek 生成该品类的真实进口商名单。"""
    response = httpx.post(
        f"{settings.ai_base_url.rstrip('/')}/chat/completions",
        json={
            "model": settings.ai_model,
            "messages": build_discover_messages(category, hs_code),
            "temperature": 0.3,
            # 推理模型思维链 ~7000 tokens
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


def make_discover_buyers_handler(settings: Settings | None = None):
    """对产品触发 AI 买家发现：生成名单 → 入库 → 批量排补全任务。"""

    def handler(session: Session, payload: dict) -> None:
        from app.infrastructure.enrichment import PermanentJobError

        category = str(payload.get("category") or "").strip()
        if not category:
            raise PermanentJobError("品类描述不能为空")

        cfg = settings or get_settings()
        if not cfg.ai_api_key:
            raise PermanentJobError("未配置 AI Key，无法自动发现买家")

        # 1. AI 生成名单
        hs_code = str(payload.get("hs_code") or "").strip()
        buyers = call_deepseek_discover(category, hs_code, cfg)

        # 2. 逐家入库（已存在的跳过）+ 排补全任务
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
            # 对新公司排 find_contacts（走免费目录+爬虫+AI 全链路）
            queue.enqueue("find_contacts", {"company_id": company.id})

        session.commit()

    return handler
