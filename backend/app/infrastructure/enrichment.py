"""WP4 补全：按次调用日志（每日上限/审计/30 天不重复查）与任务处理器。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.contacts import website_confidence
from app.domain.ports import ContactFinder as ContactFinderProtocol
from app.domain.ports import WebsiteDirectory as WebsiteDirectoryProtocol
from app.infrastructure.contact_finders import make_finder
from app.infrastructure.contact_repository import SqlContactRepository
from app.infrastructure.crawler import CrawlBlocked, WebsiteCrawler
from app.infrastructure.jobs import PermanentJobError, QuotaDeferred, SqlJobQueue
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
        self, company_ids: list[int], days: int = 30, ok_only: bool = True
    ) -> set[int]:
        """days 天内查过补全的公司。ok_only=True 只算成功外呼（失败调用不黑名单 30 天）。"""
        if not company_ids:
            return set()
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = select(EnrichmentCallORM.company_id).where(
            EnrichmentCallORM.company_id.in_(company_ids),
            EnrichmentCallORM.called_at >= since,
        )
        if ok_only:
            stmt = stmt.where(EnrichmentCallORM.ok.is_(True))
        return set(self._session.scalars(stmt))

    def reserve(self, provider: str, company_id: int, cap: int) -> int | None:
        """额度预留：advisory lock + 独立短事务内计数并插入审计行（ok=False）。

        多 worker 并发下互斥，杜绝「同时读到 used<cap 而双双外呼」的超扣；
        返回审计行 id，额度已满返回 None。外呼成功后调 mark_ok 翻转。
        """
        from sqlalchemy import text as sql_text
        from sqlalchemy.orm import Session as _S

        engine = self._session.bind
        with _S(engine) as tx:
            tx.execute(sql_text("select pg_advisory_xact_lock(918273645)"))
            used = tx.scalar(
                sql_text(
                    "select coalesce(sum(credits_used), 0) from enrichment_calls "
                    "where called_at::date = current_date"
                )
            )
            if int(used or 0) >= cap:
                tx.rollback()
                return None
            row = EnrichmentCallORM(
                provider=provider, company_id=company_id, credits_used=1, ok=False
            )
            tx.add(row)
            tx.flush()
            record_id = row.id
            tx.commit()  # 提交即释放 advisory lock
            return record_id

    def mark_ok(self, record_id: int) -> None:
        from sqlalchemy.orm import Session as _S

        engine = self._session.bind
        with _S(engine) as tx:
            row = tx.get(EnrichmentCallORM, record_id)
            if row is not None:
                row.ok = True
                tx.commit()


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


def _normalize_website_url(raw: str) -> str:
    website = (raw or "").strip()
    if website and "://" not in website:
        website = f"https://{website}"  # 入库规范化为绝对 URL（F9）
    return website


def make_find_contacts_handler(
    finder: ContactFinderProtocol | None = None,
    settings: Settings | None = None,
    directory: WebsiteDirectoryProtocol | None = None,
    domain_guesser=None,
):
    """补全联系人：免费目录源（官网发现）优先，计量 finder 兜底/查联系人。

    domain_guesser: 可选的域名猜测探测函数（生产由 worker 注入，测试跳过）。
    """

    def handler(session: Session, payload: dict) -> None:
        company_id = int(payload["company_id"])
        company = session.get(CompanyORM, company_id)
        if company is None:
            raise PermanentJobError(f"公司 {company_id} 不存在")
        cfg = settings or get_settings()
        log = SqlEnrichmentLog(session)

        # F5 幂等短路：30 天内成功外呼过 → 不再调用补全服务（含崩溃重试场景）
        if company_id in log.companies_queried_within([company_id]):
            return

        had_usable = _website_usable(company)

        # 免费目录源（如 Wikidata）：仅域名发现，不占计量额度；
        # 高置信自动采用并继续查联系人，中低置信只写候选等人工确认。
        if not had_usable and directory is not None:
            found = directory.search(_company_display_name(company), company.country)
            if found is not None:
                confidence = website_confidence(
                    found.matched_name,
                    company.normalized_name,
                    found.country,
                    company.country,
                )
                company.website = _normalize_website_url(found.website)
                company.website_source = found.source
                company.website_confidence = confidence
                session.flush()
                log.record(found.source, company_id, credits_used=0)
                if confidence != "high":
                    session.commit()  # 候选落库即止，不进计量路径
                    return
                company.website_confirmed = True  # 自动采用
                had_usable = True
                session.commit()  # 采纳先落库：后续邮箱写入失败不再冲掉官网
                if found.email:  # 目录源偶得的公开邮箱（如 P968）直接入库
                    SqlContactRepository(session).add(
                        company_id, name=None, title="", email=found.email,
                        phone=None, source=found.source, source_ref=f"{found.source}:P968",
                    )

        # 域名猜测兜底：Wikidata 没找到时，从公司名猜常见域名（免费，不占额度）
        if not had_usable and domain_guesser is not None:
            from app.domain.guess_domain import guess_domains

            for domain in guess_domains(_company_display_name(company)):
                candidate = f"https://{domain}"
                if domain_guesser(candidate):  # 返回 True = 域名可达
                    company.website = candidate
                    company.website_source = "guess"
                    company.website_confidence = "medium"
                    session.flush()
                    log.record("guess", company_id, credits_used=0)
                    session.commit()
                    break

        # F3 额度原子预留：先记账（advisory lock）再外呼；额度是日滚动资源，
        # 用尽 → 延期到明日（F4），不是失败。
        provider = "hunter" if cfg.hunter_api_key else "fake"
        record_id = log.reserve(provider, company_id, cap=cfg.enrich_daily_cap)
        if record_id is None:
            raise QuotaDeferred(
                datetime.now(UTC) + timedelta(days=1),
                f"今日补全额度已用尽（上限 {cfg.enrich_daily_cap}），延期到明日重跑",
            )

        # 计量 finder：有官网按域名查联系人；无官网做域名发现（3.7 第 1 条）。
        website_raw = (company.website or "").strip()
        active_finder = finder or make_finder(cfg)
        result = active_finder.find(
            _website_host(website_raw) if website_raw else "",
            _company_display_name(company),
            company.country,
        )

        adopted_high = False
        if result.domain and not had_usable:
            confidence = website_confidence(
                result.domain_company_name or "",
                company.normalized_name,
                result.domain_country or "",
                company.country,
            )
            company.website = _normalize_website_url(result.domain)
            company.website_source = "finder"
            company.website_confidence = confidence
            if confidence == "high":
                company.website_confirmed = True  # 自动采用
                adopted_high = True
            session.flush()

        if not (had_usable or adopted_high):
            log.mark_ok(record_id)  # 已外呼（产出候选）：计入成功，防 30 天内重复查
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

        log.mark_ok(record_id)  # 联系人落库后翻转审计；此后崩溃重试会被短路（F5）

        # 自动验证（DEV-SPEC 3.7 第 3 条）：有 Hunter key 才排验证任务
        if new_ids and cfg.hunter_api_key:
            queue = SqlJobQueue(session)
            for contact_id in new_ids:
                queue.enqueue("verify_email", {"contact_id": contact_id})

    return handler


def make_crawl_website_handler(
    crawler: WebsiteCrawler | None = None,
    settings: Settings | None = None,
    ai_extractor=None,
):
    """抓企业自有官网公开页：robots/限速/SSRF 全约束，结果 source=website。

    配置 AI Key 且当日未超上限时，爬虫附带 AI 联系人提取（联系页、失败兜底）。
    """

    def handler(session: Session, payload: dict) -> None:
        company_id = int(payload["company_id"])
        company = session.get(CompanyORM, company_id)
        if company is None:
            raise PermanentJobError(f"公司 {company_id} 不存在")
        if not _website_usable(company):
            raise PermanentJobError("该企业没有已确认的官网，先填写并确认官网再抓取")

        cfg = settings or get_settings()
        active_ai = ai_extractor
        if active_ai is None and cfg.ai_api_key:
            ai_used = sum(
                1 for r in session.scalars(
                    select(EnrichmentCallORM).where(
                        EnrichmentCallORM.provider == "ai-extract",
                        func.date(EnrichmentCallORM.called_at) == func.current_date(),
                    )
                )
            )
            if ai_used < cfg.ai_daily_cap:
                from app.infrastructure.ai_extractor import make_ai_extractor

                active_ai = make_ai_extractor(cfg)

        active_crawler = crawler or WebsiteCrawler(ai_extractor=active_ai)
        try:
            result = active_crawler.crawl(company.website.strip())
        except CrawlBlocked as exc:
            raise PermanentJobError(f"官网抓取被拒：{exc}") from exc
        if result.blocked_reason:
            raise RuntimeError(result.blocked_reason)  # 首页失败可能瞬态，按可重试处理

        if active_ai is not None and getattr(active_ai, "calls", 0):
            SqlEnrichmentLog(session).record(
                "ai-extract", company_id, credits_used=0
            )  # AI 调用入审计（0 计量额度，日上限按 provider 计数）

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
    directory: WebsiteDirectoryProtocol | None = None,
) -> dict:
    """worker 与 API 共用的处理器注册表（finder/crawler/directory 可注入替身）。

    directory 默认 None：测试（含冒烟）保持离线；生产由 worker 显式接线真实目录源。
    """
    from app.infrastructure.discover import make_discover_buyers_handler

    def _probe_domain(url: str) -> bool:
        import httpx
        try:
            r = httpx.head(url, timeout=5, follow_redirects=True)
            return r.status_code < 400
        except Exception:  # noqa: BLE001
            return False

    return {
        "find_contacts": make_find_contacts_handler(
            finder, settings, directory, domain_guesser=_probe_domain,
        ),
        "crawl_website": make_crawl_website_handler(crawler, settings),
        "verify_email": make_verify_email_handler(finder, settings),
        "discover_buyers": make_discover_buyers_handler(settings),
    }
