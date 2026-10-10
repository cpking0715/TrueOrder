"""WP4 补全：按次调用日志（每日上限/审计/30 天不重复查）与任务处理器。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.contacts import website_confidence
from app.domain.ports import ContactFinder as ContactFinderProtocol
from app.infrastructure.contact_finders import make_finder
from app.infrastructure.contact_repository import SqlContactRepository
from app.infrastructure.crawler import CrawlBlocked, WebsiteCrawler
from app.infrastructure.jobs import PermanentJobError, SqlJobQueue
from app.infrastructure.orm import CompanyORM, ContactORM, EnrichmentCallORM


class SqlEnrichmentLog:
    def __init__(self, session: Session) -> None:
        self._session = session

    def calls_today(self, today: date | None = None) -> int:
        today = today or datetime.now(UTC).date()
        return int(
            self._session.scalar(
                select(func.count()).select_from(EnrichmentCallORM).where(
                    func.date(EnrichmentCallORM.called_at) == today
                )
            )
            or 0
        )

    def record(
        self, provider: str, company_id: int, credits_used: int = 1, ok: bool = True
    ) -> None:
        self._session.add(
            EnrichmentCallORM(
                provider=provider, company_id=company_id, credits_used=credits_used, ok=ok
            )
        )
        self._session.flush()

    def companies_queried_within(
        self, company_ids: list[int], days: int = 30
    ) -> set[int]:
        """days 天内查过补全的公司（无论成败）——批量补全时不重复查。"""
        if not company_ids:
            return set()
        since = datetime.now(UTC) - timedelta(days=days)
        rows = self._session.scalars(
            select(EnrichmentCallORM.company_id).where(
                EnrichmentCallORM.company_id.in_(company_ids),
                EnrichmentCallORM.called_at >= since,
            )
        )
        return set(rows)


def _company_display_name(company: CompanyORM) -> str:
    return (company.name_variants or [company.normalized_name])[0]


def _website_host(website: str) -> str:
    """官网 URL → 主机名（finder 按域名查询；带 scheme/path 时剥掉）。"""
    from urllib.parse import urlparse

    raw = website.strip()
    parsed = urlparse(raw if "//" in raw else f"https://{raw}")
    return (parsed.hostname or raw).lower()


def _website_usable(company: CompanyORM) -> bool:
    """已确认，或补全返回的高置信候选（DEV-SPEC 3.7 第 1 条）。"""
    if not (company.website or "").strip():
        return False
    return bool(company.website_confirmed) or company.website_confidence == "high"


def make_find_contacts_handler(
    finder: ContactFinderProtocol | None = None, settings: Settings | None = None
):
    """按官网域名查联系人：额度检查 → finder 查询 → 域名候选回写 → 联系人入库 → 排验证。"""

    def handler(session: Session, payload: dict) -> None:
        company_id = int(payload["company_id"])
        company = session.get(CompanyORM, company_id)
        if company is None:
            raise PermanentJobError(f"公司 {company_id} 不存在")
        cfg = settings or get_settings()
        log = SqlEnrichmentLog(session)
        used = log.calls_today()
        if used >= cfg.enrich_daily_cap:
            raise PermanentJobError(
                f"今日补全调用已达上限（{used}/{cfg.enrich_daily_cap}），明天再试"
            )

        # 域名发现（3.7 第 1 条）：无官网/官网未确认时仍可按公司名查域名；
        # 高置信自动采用并继续查联系人，中低置信只写候选等人工确认。
        had_usable = _website_usable(company)
        website_raw = (company.website or "").strip()
        active_finder = finder or make_finder(cfg)
        result = active_finder.find(
            _website_host(website_raw) if website_raw else "",
            _company_display_name(company),
        )
        provider = "hunter" if cfg.hunter_api_key else "fake"
        log.record(provider, company_id)

        adopted_high = False
        if result.domain and not had_usable:
            confidence = website_confidence(
                result.domain_company_name or "",
                company.normalized_name,
                result.domain_country or "",
                company.country,
            )
            company.website = result.domain
            company.website_source = "finder"
            company.website_confidence = confidence
            if confidence == "high":
                company.website_confirmed = True  # 自动采用
                adopted_high = True
            session.flush()

        if not (had_usable or adopted_high):
            return  # 中低置信候选：联系人不自动查，等用户确认官网

        repo = SqlContactRepository(session)
        new_ids: list[int] = []
        for c in result.contacts:
            added = repo.add(
                company_id,
                name=c.name,
                title=c.title,
                email=c.email,
                phone=c.phone,
                source="finder",
                source_ref=c.source_ref,
            )
            if added.contact is not None:
                new_ids.append(added.contact.contact_id)

        # 自动验证（DEV-SPEC 3.7 第 3 条）：有 Hunter key 才排验证任务
        if new_ids and cfg.hunter_api_key:
            queue = SqlJobQueue(session)
            for contact_id in new_ids:
                queue.enqueue("verify_email", {"contact_id": contact_id})

    return handler


def make_crawl_website_handler(
    crawler: WebsiteCrawler | None = None, settings: Settings | None = None
):
    """抓企业自有官网公开页：robots/限速/SSRF 全约束，结果 source=website。"""

    def handler(session: Session, payload: dict) -> None:
        company_id = int(payload["company_id"])
        company = session.get(CompanyORM, company_id)
        if company is None:
            raise PermanentJobError(f"公司 {company_id} 不存在")
        if not _website_usable(company):
            raise PermanentJobError("该企业没有已确认的官网，先填写并确认官网再抓取")

        active_crawler = crawler or WebsiteCrawler()
        try:
            result = active_crawler.crawl(company.website.strip())
        except CrawlBlocked as exc:
            raise PermanentJobError(f"官网抓取被拒：{exc}") from exc
        if result.blocked_reason:
            raise RuntimeError(result.blocked_reason)  # 首页失败可能瞬态，按可重试处理

        repo = SqlContactRepository(session)
        for c in result.contacts:
            repo.add(
                company_id,
                name=c.name,
                title=c.title,
                email=c.email,
                phone=c.phone,
                source="website",
                source_ref=c.source_ref,
            )

    return handler


def make_verify_email_handler(
    finder: ContactFinderProtocol | None = None, settings: Settings | None = None
):
    """邮箱可达性验证：Hunter Verifier → verify_status；无 key 时跳过（保持 unknown）。"""

    def handler(session: Session, payload: dict) -> None:
        cfg = settings or get_settings()
        if not cfg.hunter_api_key:
            return
        contact = session.get(ContactORM, int(payload["contact_id"]))
        if contact is None or not contact.email:
            return
        active_finder = finder or make_finder(cfg)
        contact.verify_status = active_finder.verify(contact.email)
        session.commit()

    return handler


def build_registry(
    settings: Settings | None = None,
    finder: ContactFinderProtocol | None = None,
    crawler: WebsiteCrawler | None = None,
) -> dict:
    """worker 与 API 共用的处理器注册表（finder/crawler 可注入测试替身）。"""
    return {
        "find_contacts": make_find_contacts_handler(finder, settings),
        "crawl_website": make_crawl_website_handler(crawler, settings),
        "verify_email": make_verify_email_handler(finder, settings),
    }
