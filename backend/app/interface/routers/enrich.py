"""WP4 补全路由：单公司查找、批量补全（估计→确认）、官网确认、额度用量。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.contact_repository import SqlContactRepository
from app.infrastructure.enrichment import SqlEnrichmentLog
from app.infrastructure.jobs import SqlJobQueue
from app.infrastructure.orm import CompanyORM
from app.infrastructure.queries import BuyerQueryFilters, SqlBuyerQueries
from app.interface.deps import get_buyer_queries, get_contact_repository, get_session
from app.interface.schemas import CompanyWebsiteOut

router = APIRouter(prefix="/api", tags=["enrich"])


class JobCreatedOut(BaseModel):
    job_id: int
    kind: str


class EnrichEstimateOut(BaseModel):
    candidates: int = 0  # 当前筛选下可补全的企业数（已扣两类跳过）
    skipped_has_contacts: int = 0
    skipped_queried_recently: int = 0
    capped_by_quota: int = 0  # 因当日剩余额度被截掉的数量
    credits_needed: int = 0
    daily_cap: int = 0
    used_today: int = 0


class EnrichConfirmIn(BaseModel):
    tier: str | None = None
    q: str | None = None
    country: str | None = None
    min_shipments: int | None = Field(default=None, ge=1)
    limit: int = Field(default=10, ge=1, le=50)
    confirm: bool = False


class EnrichExecutedOut(EnrichEstimateOut):
    enqueued: int = 0
    job_ids: list[int] = []


class EnrichUsageOut(BaseModel):
    provider: str
    configured: bool
    daily_cap: int
    used_today: int
    remaining: int


def _get_company(session: Session, company_id: int) -> CompanyORM:
    company = session.get(CompanyORM, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"公司 {company_id} 不存在")
    return company


@router.post("/companies/{company_id}/find-contacts", response_model=JobCreatedOut, status_code=202)
def find_contacts(
    company_id: int,
    method: str = "finder",
    session: Session = Depends(get_session),
):
    """对单个选定企业触发补全：finder=按域名/公司名查联系人，website=抓官网公开页。"""
    if method not in ("finder", "website"):
        raise HTTPException(status_code=422, detail="method 必须是 finder 或 website")
    _get_company(session, company_id)
    kind = "find_contacts" if method == "finder" else "crawl_website"
    queue = SqlJobQueue(session)
    job_id = queue.enqueue(kind, {"company_id": company_id})
    return JobCreatedOut(job_id=job_id, kind=kind)


@router.post("/companies/{company_id}/website/confirm", response_model=CompanyWebsiteOut)
def confirm_website(
    company_id: int,
    repo: SqlContactRepository = Depends(get_contact_repository),
):
    """把中低置信的域名候选确认为官网（确认后才允许继续查联系人/抓取）。"""
    result = repo.update_website(company_id, None, True)
    if result is None:
        raise HTTPException(status_code=404, detail=f"公司 {company_id} 不存在")
    website, confirmed = result
    company = _get_company(repo._session, company_id)  # noqa: SLF001 - 取置信度展示
    return CompanyWebsiteOut(
        company_id=company_id,
        website=website,
        website_confirmed=confirmed,
        website_source=company.website_source,
        website_confidence=company.website_confidence,
    )


@router.get("/enrichment/usage", response_model=EnrichUsageOut)
def enrichment_usage(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    provider = "hunter" if settings.hunter_api_key else "fake（未配置 Hunter Key）"
    used = SqlEnrichmentLog(session).calls_today()
    return {
        "provider": provider,
        "configured": bool(settings.hunter_api_key),
        "daily_cap": settings.enrich_daily_cap,
        "used_today": used,
        "remaining": max(settings.enrich_daily_cap - used, 0),
    }


@router.post("/products/{product_id}/buyers/enrich", response_model=EnrichExecutedOut)
def enrich_buyers(
    product_id: int,
    payload: EnrichConfirmIn,
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
    repo: SqlContactRepository = Depends(get_contact_repository),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """批量补全当前筛选的前 N 家：不带 confirm 只返回额度估计；confirm=true 才入队。"""
    from app.interface.routers.products import _default_audience

    audience = _default_audience(queries, product_id)
    tiers = [payload.tier] if payload.tier else ["potential", "precise"]
    buyers: list = []
    for tier in tiers:
        filters = BuyerQueryFilters(
            product_id=product_id,
            audience=audience,
            tier=tier,
            q=payload.q,
            country=payload.country,
            min_shipments=payload.min_shipments,
            order="shipments",
            limit=payload.limit + 50,  # 余量给跳过逻辑
            offset=0,
        )
        buyers.extend(queries.query_buyers(filters)[0])
    buyers.sort(key=lambda b: (-b.shipments, b.name))
    candidates = buyers[: payload.limit]

    log = SqlEnrichmentLog(session)
    queried = log.companies_queried_within([b.company_id for b in candidates])
    has_contacts = repo.companies_with_contacts([b.company_id for b in candidates])
    eligible = [
        b for b in candidates
        if b.company_id not in has_contacts and b.company_id not in queried
    ]

    used = log.calls_today()
    remaining = max(settings.enrich_daily_cap - used, 0)
    capped = max(len(eligible) - remaining, 0)
    to_run = eligible[:remaining]

    estimate = EnrichEstimateOut(
        candidates=len(eligible),
        skipped_has_contacts=sum(1 for b in candidates if b.company_id in has_contacts),
        skipped_queried_recently=sum(1 for b in candidates if b.company_id in queried),
        capped_by_quota=capped,
        credits_needed=len(to_run),
        daily_cap=settings.enrich_daily_cap,
        used_today=used,
    )
    if not payload.confirm:
        return estimate

    queue = SqlJobQueue(session)
    job_ids = [queue.enqueue("find_contacts", {"company_id": b.company_id}) for b in to_run]
    executed = EnrichExecutedOut(**estimate.__dict__, enqueued=len(job_ids), job_ids=job_ids)
    return executed
