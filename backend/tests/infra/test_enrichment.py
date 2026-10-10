"""WP4 处理器与补全日志（真 PostgreSQL；finder/crawler 全部注入替身，不访问外网）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.entities import FinderResult, FoundContact
from app.infrastructure.crawler import CrawlBlocked, CrawlResult
from app.infrastructure.enrichment import (
    SqlEnrichmentLog,
    make_crawl_website_handler,
    make_find_contacts_handler,
)
from app.infrastructure.jobs import SqlJobQueue, Worker
from app.infrastructure.orm import CompanyORM

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
CFG = Settings(hunter_api_key="")


@pytest.fixture()
def queue(session: Session) -> SqlJobQueue:
    return SqlJobQueue(session)


@pytest.fixture()
def company(session: Session) -> CompanyORM:
    c = CompanyORM(
        normalized_name="BROOKLYN APPAREL",
        country="US",
        name_variants=["Brooklyn Apparel LLC"],
    )
    session.add(c)
    session.commit()
    return c


class FakeFinder:
    def __init__(self, result: FinderResult) -> None:
        self._result = result
        self.calls: list[str] = []

    def find(self, domain: str, company_name: str) -> FinderResult:
        self.calls.append(domain)
        return self._result

    def verify(self, email: str) -> str:
        return "valid"


def contacts_of(session: Session, company_id: int) -> list:
    from app.infrastructure.contact_repository import SqlContactRepository

    return SqlContactRepository(session).list_by_company(company_id)


class Test按官网补全:
    def test_已确认官网_联系人入库带来源(self, session, company, queue):
        company.website = "https://brooklynapparel.com"
        company.website_confirmed = True
        session.commit()
        finder = FakeFinder(
            FinderResult(
                domain="brooklynapparel.com",
                domain_company_name="Brooklyn Apparel LLC",
                domain_country="US",
                contacts=(
                    FoundContact(
                        name="John Doe",
                        title="Buyer",
                        email="john@brooklynapparel.com",
                        source_ref="hunter:domain-search",
                    ),
                ),
            )
        )
        job_id = queue.enqueue("find_contacts", {"company_id": company.id})
        Worker(queue, {"find_contacts": make_find_contacts_handler(finder, CFG)}).run_once(NOW)

        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "done"
        assert finder.calls == ["brooklynapparel.com"]
        contacts = contacts_of(session, company.id)
        assert [c.email for c in contacts] == ["john@brooklynapparel.com"]
        assert contacts[0].source == "finder"
        assert contacts[0].source_ref == "hunter:domain-search"

    def test_无官网时走域名发现_高置信自动采用并查联系人(self, session, company, queue):
        finder = FakeFinder(
            FinderResult(
                domain="brooklynapparel.com",
                domain_company_name="Brooklyn Apparel LLC",
                domain_country="US",
                contacts=(FoundContact(name="John Doe", email="john@brooklynapparel.com"),),
            )
        )
        job_id = queue.enqueue("find_contacts", {"company_id": company.id})
        Worker(queue, {"find_contacts": make_find_contacts_handler(finder, CFG)}).run_once(NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "done"
        session.expire_all()
        refreshed = session.get(CompanyORM, company.id)
        assert refreshed.website == "brooklynapparel.com"
        assert refreshed.website_confidence == "high"
        assert refreshed.website_confirmed is True  # 高置信自动采用
        assert [c.email for c in contacts_of(session, company.id)] == ["john@brooklynapparel.com"]

    def test_域名发现中低置信_只写候选不查联系人(self, session, company, queue):
        finder = FakeFinder(
            FinderResult(
                domain="maybe.com",
                domain_company_name="别的公司",
                domain_country="US",
                contacts=(FoundContact(email="someone@maybe.com"),),
            )
        )
        queue.enqueue("find_contacts", {"company_id": company.id})
        Worker(queue, {"find_contacts": make_find_contacts_handler(finder, CFG)}).run_once(NOW)
        session.expire_all()
        refreshed = session.get(CompanyORM, company.id)
        assert refreshed.website == "maybe.com"
        assert refreshed.website_confidence == "low"
        assert refreshed.website_confirmed is False
        assert contacts_of(session, company.id) == []  # 候选不自动查联系人

    def test_公司不存在_永久失败(self, session, queue):
        job_id = queue.enqueue("find_contacts", {"company_id": 99999})
        Worker(queue, {"find_contacts": make_find_contacts_handler(None, CFG)}).run_once(NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "failed"

    def test_域名候选回写_官网为空且名称国家全中(self, session, company, queue):
        company.website = "https://brooklynapparel.com"
        company.website_confirmed = True
        session.commit()
        finder = FakeFinder(
            FinderResult(domain="brooklynapparel.com", domain_company_name="Brooklyn Apparel LLC",
                         domain_country="US", contacts=())
        )
        session.execute(
            CompanyORM.__table__.update().where(CompanyORM.id == company.id).values(website="")
        )
        session.commit()
        queue.enqueue("find_contacts", {"company_id": company.id})
        Worker(queue, {"find_contacts": make_find_contacts_handler(finder, CFG)}).run_once(NOW)
        session.expire_all()
        refreshed = session.get(CompanyORM, company.id)
        assert refreshed.website == "brooklynapparel.com"
        assert refreshed.website_source == "finder"
        assert refreshed.website_confidence == "high"

    def test_每日上限_超额永久失败(self, session, company, queue):
        company.website = "https://x.com"
        company.website_confirmed = True
        session.commit()
        cfg = Settings(hunter_api_key="", enrich_daily_cap=1)
        log = SqlEnrichmentLog(session)
        log.record("fake", company.id)
        session.commit()
        job_id = queue.enqueue("find_contacts", {"company_id": company.id})
        Worker(queue, {"find_contacts": make_find_contacts_handler(None, cfg)}).run_once(NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "failed"
        assert "上限" in (job.last_error or "")

    def test_无key时验证任务不排(self, session, company, queue):
        company.website = "https://brooklynapparel.com"
        company.website_confirmed = True
        session.commit()
        finder = FakeFinder(
            FinderResult(contacts=(FoundContact(email="john@brooklynapparel.com"),))
        )
        queue.enqueue("find_contacts", {"company_id": company.id})
        Worker(queue, {"find_contacts": make_find_contacts_handler(finder, CFG)}).run_once(NOW)
        assert queue.list_jobs(status="pending") == []  # 无 hunter key → 不排 verify_email


class Test官网抓取处理器:
    def test_抓取结果入库source_website(self, session, company, queue):
        company.website = "https://brooklynapparel.com"
        company.website_confirmed = True
        session.commit()

        class FakeCrawler:
            def crawl(self, url: str) -> CrawlResult:
                return CrawlResult(
                    pages_fetched=[url],
                    contacts=[
                        FoundContact(
                            email="info@brooklynapparel.com", source_ref=f"website:{url}"
                        )
                    ],
                )

        job_id = queue.enqueue("crawl_website", {"company_id": company.id})
        worker = Worker(queue, {"crawl_website": make_crawl_website_handler(FakeCrawler(), CFG)})
        worker.run_once(NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "done"
        contacts = contacts_of(session, company.id)
        assert contacts[0].source == "website"
        assert contacts[0].source_ref.startswith("website:")

    def test_robots禁抓_永久失败(self, session, company, queue):
        company.website = "https://no.com"
        company.website_confirmed = True
        session.commit()

        class BlockedCrawler:
            def crawl(self, url: str) -> CrawlResult:
                raise CrawlBlocked("robots.txt 不允许抓取该站点")

        job_id = queue.enqueue("crawl_website", {"company_id": company.id})
        worker = Worker(queue, {"crawl_website": make_crawl_website_handler(BlockedCrawler(), CFG)})
        worker.run_once(NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "failed"
        assert "robots" in (job.last_error or "")


class Test补全日志:
    def test_当日计数与三十天内查过的公司(self, session, company):
        log = SqlEnrichmentLog(session)
        assert log.calls_today() == 0
        log.record("fake", company.id)
        session.commit()
        assert log.calls_today() == 1
        assert log.companies_queried_within([company.id, 99999]) == {company.id}

    def test_重复导入同邮箱只入一条(self, session, company, queue):
        company.website = "https://brooklynapparel.com"
        company.website_confirmed = True
        session.commit()
        finder = FakeFinder(FinderResult(contacts=(FoundContact(email="dup@x.com"),)))
        for _ in range(2):
            queue.enqueue("find_contacts", {"company_id": company.id})
            Worker(queue, {"find_contacts": make_find_contacts_handler(finder, CFG)}).run_once(NOW)
        assert len(contacts_of(session, company.id)) == 1
