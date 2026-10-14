"""WP4 处理器与补全日志（真 PostgreSQL；finder/crawler 全部注入替身，不访问外网）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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

# 动态基准时间（略超前）：入队默认 run_after=now()，固定日期会在跨天后让任务永不到期
NOW = datetime.now(UTC) + timedelta(hours=1)  # 余量放大：全量套件运行数十秒，5 秒会过期
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

    def find(self, domain: str, company_name: str, company_country: str = "") -> FinderResult:
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
        assert refreshed.website == "https://brooklynapparel.com"
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
        assert refreshed.website == "https://maybe.com"
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
        assert refreshed.website == "https://brooklynapparel.com"
        assert refreshed.website_source == "finder"
        assert refreshed.website_confidence == "high"

    def test_每日额度用尽任务延期到明日不再计数失败(self, session, company, queue):
        company.website = "https://x.com"
        company.website_confirmed = True
        session.commit()
        cfg = Settings(hunter_api_key="", enrich_daily_cap=1)
        log = SqlEnrichmentLog(session)
        # ok=False：占用额度但不构成「成功外呼」，不触发 30 天短路
        log.record("fake", company.id, ok=False)
        session.commit()
        job_id = queue.enqueue("find_contacts", {"company_id": company.id})
        Worker(queue, {"find_contacts": make_find_contacts_handler(None, cfg)}).run_once(NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "pending"  # 额度是日滚动资源：延期而非失败
        assert job.run_after and job.run_after > NOW
        assert job.attempts == 0  # 延期不算失败
        assert "额度" in (job.last_error or "")

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

    @pytest.mark.parametrize("db_tz", ["Asia/Shanghai", "America/Los_Angeles"])
    def test_当日计数按UTC自然日_不受数据库会话时区影响(self, session, company, db_tz):
        """回归：曾用 date(called_at)=今天(UTC)，取的是 PG 会话时区，本地零点附近漂移。"""
        from datetime import timedelta as _td

        from sqlalchemy import text as _text

        from app.core.timeutil import utc_day_bounds
        from app.infrastructure.orm import EnrichmentCallORM

        session.execute(_text(f"SET TIME ZONE '{db_tz}'"))
        start, _end = utc_day_bounds()
        session.add_all([
            EnrichmentCallORM(provider="fake", company_id=company.id,
                              called_at=start + _td(minutes=1)),   # 今天（UTC）
            EnrichmentCallORM(provider="fake", company_id=company.id,
                              called_at=start - _td(minutes=1)),   # 昨天（UTC）
        ])
        session.commit()
        log = SqlEnrichmentLog(session)
        assert log.calls_today() == 1
        assert log.reserve("fake", company.id, cap=2) is not None  # 已用 1 < 2
        assert log.reserve("fake", company.id, cap=2) is None      # 已用 2 = cap

    def test_重复导入同邮箱只入一条(self, session, company, queue):
        company.website = "https://brooklynapparel.com"
        company.website_confirmed = True
        session.commit()
        finder = FakeFinder(FinderResult(contacts=(FoundContact(email="dup@x.com"),)))
        for _ in range(2):
            queue.enqueue("find_contacts", {"company_id": company.id})
            Worker(queue, {"find_contacts": make_find_contacts_handler(finder, CFG)}).run_once(NOW)
        assert len(contacts_of(session, company.id)) == 1


CFG_KEY = Settings(hunter_api_key="test-key")


class Test审阅修复轮WP4:
    """Brief-4 findings：verify_email 约束、fake 域名发现、额度原子性、重试幂等。"""

    def test_F1_有hunter_key时自动排verify_email且可消费(self, session, company, queue):
        from sqlalchemy import select

        from app.infrastructure.orm import ContactORM

        company.website = "https://brooklynapparel.com"
        company.website_confirmed = True
        session.commit()
        finder = FakeFinder(FinderResult(contacts=(FoundContact(email="v@x.com"),)))
        queue.enqueue("find_contacts", {"company_id": company.id})
        handlers = {
            "find_contacts": make_find_contacts_handler(finder, CFG_KEY),
            "verify_email": __import__("app.infrastructure.enrichment", fromlist=["x"])
            .make_verify_email_handler(finder, CFG_KEY),
        }
        Worker(queue, handlers).run_once(NOW)
        verify_jobs = queue.list_jobs(status="pending")
        assert any(j.kind == "verify_email" for j in verify_jobs), "应排 verify_email（P0 回归）"
        Worker(queue, handlers).run_once(NOW)  # 消费 verify
        contact = session.scalars(select(ContactORM).where(ContactORM.email == "v@x.com")).one()
        assert contact.verify_status == "valid"

    def test_F2_真实fake补全器域名发现_高置信自动采用并写联系人(self, session, company, queue):
        # 不注入替身：走 make_finder() → FakeContactFinder（演示路径本身要闭环）
        queue.enqueue("find_contacts", {"company_id": company.id})
        Worker(queue, {"find_contacts": make_find_contacts_handler(None, CFG)}).run_once(NOW)
        session.expire_all()
        refreshed = session.get(CompanyORM, company.id)
        assert refreshed.website_confirmed is True, (
            f"fake 应回显公司国家使置信度达 high：conf={refreshed.website_confidence}"
        )
        assert contacts_of(session, company.id), "高置信自动采用后联系人应入库"

    def test_F3_额度预留并发互斥(self, session, company, queue, engine):
        from sqlalchemy import select as sel
        from sqlalchemy.orm import Session as S

        company.website = "https://x.com"
        company.website_confirmed = True
        company_b = CompanyORM(
            normalized_name="OTHER CO", country="US", name_variants=["Other Co"],
            website="https://y.com", website_confirmed=True,
        )
        session.add(company_b)
        session.commit()
        cfg = Settings(hunter_api_key="", enrich_daily_cap=1)
        other = S(engine)
        q1, q2 = SqlJobQueue(session), SqlJobQueue(other)
        j1 = q1.enqueue("find_contacts", {"company_id": company.id})
        j2 = q2.enqueue("find_contacts", {"company_id": company_b.id})
        # 两会话交错执行、cap=1：第二家必须被延期而不是双双外呼记账
        Worker(q1, {"find_contacts": make_find_contacts_handler(None, cfg)}).run_once(NOW)
        Worker(q2, {"find_contacts": make_find_contacts_handler(None, cfg)}).run_once(NOW)
        other.close()
        from app.infrastructure.orm import EnrichmentCallORM
        rows = session.scalars(sel(EnrichmentCallORM)).all()
        assert len(rows) == 1, f"cap=1 时只允许一次记账，实际 {len(rows)}"
        jobs = {j.id: j for j in q1.list_jobs()}
        assert jobs[j1].status == "done"
        assert jobs[j2].status == "pending", jobs[j2].last_error
        assert jobs[j2].run_after and jobs[j2].run_after > NOW

    def test_F5_三十天内成功查过不再外呼(self, session, company, queue):
        company.website = "https://brooklynapparel.com"
        company.website_confirmed = True
        session.commit()
        finder = FakeFinder(FinderResult(contacts=(FoundContact(email="one@x.com"),)))
        handler = make_find_contacts_handler(finder, CFG)
        for _ in range(2):  # 第二次模拟崩溃后重试/用户再点
            queue.enqueue("find_contacts", {"company_id": company.id})
            Worker(queue, {"find_contacts": handler}).run_once(NOW)
        assert len(finder.calls) == 1, "成功外呼过 30 天内不得重复调用补全服务"
        assert len(contacts_of(session, company.id)) == 1


class FakeDirectory:
    def __init__(self, found) -> None:
        self._found = found
        self.calls: list[tuple[str, str]] = []

    def search(self, company_name: str, country: str):
        self.calls.append((company_name, country))
        return self._found


class Test免费目录源集成:
    """Wikidata 免费路径：命中即不烧计量额度；未命中回落计量路径。"""

    def test_高置信命中_官网自动采用且仅计量一次(self, session, company, queue):
        from sqlalchemy import select as sel

        from app.domain.entities import FoundWebsite
        from app.infrastructure.orm import EnrichmentCallORM

        finder = FakeFinder(FinderResult(contacts=(FoundContact(email="john@x.com"),)))
        directory = FakeDirectory(FoundWebsite(
            website="https://brooklynapparel.example",
            matched_name="Brooklyn Apparel LLC",
            country="US",
            email="info@brooklynapparel.example",
        ))
        queue.enqueue("find_contacts", {"company_id": company.id})
        handler = make_find_contacts_handler(finder, CFG, directory=directory)
        Worker(queue, {"find_contacts": handler}).run_once(NOW)

        session.expire_all()
        refreshed = session.get(CompanyORM, company.id)
        assert refreshed.website == "https://brooklynapparel.example"
        assert refreshed.website_source == "wikidata"  # noqa: E501
        assert refreshed.website_confidence == "high"
        assert refreshed.website_confirmed is True
        # 目录源以公司名查询；计量 finder 以采纳后的域名查联系人
        assert directory.calls == [("Brooklyn Apparel LLC", "US")]
        assert finder.calls == ["brooklynapparel.example"]
        contacts = contacts_of(session, company.id)
        emails = {c.email for c in contacts}
        assert emails == {"john@x.com", "info@brooklynapparel.example"}  # 计量 + 目录免费邮箱
        sources = {c.email: c.source for c in contacts}
        assert sources["info@brooklynapparel.example"] == "wikidata"
        # 审计：wikidata 0 额度 + 计量 1 额度
        rows = session.scalars(sel(EnrichmentCallORM).order_by(EnrichmentCallORM.id)).all()
        assert [(r.provider, r.credits_used) for r in rows] == [("wikidata", 0), ("fake", 1)]

    def test_中低置信只写候选不进计量路径(self, session, company, queue):
        from sqlalchemy import select as sel

        from app.domain.entities import FoundWebsite
        from app.infrastructure.orm import EnrichmentCallORM

        finder = FakeFinder(FinderResult(contacts=(FoundContact(email="a@b.com"),)))
        directory = FakeDirectory(FoundWebsite(
            website="https://maybe.example", matched_name="Other Corp", country="US",
        ))
        queue.enqueue("find_contacts", {"company_id": company.id})
        handler = make_find_contacts_handler(finder, CFG, directory=directory)
        Worker(queue, {"find_contacts": handler}).run_once(NOW)

        session.expire_all()
        refreshed = session.get(CompanyORM, company.id)
        assert refreshed.website == "https://maybe.example"
        assert refreshed.website_confirmed is False  # 候选等人工确认
        assert finder.calls == []  # 计量 finder 未被调用
        rows = session.scalars(sel(EnrichmentCallORM)).all()
        assert [(r.provider, r.credits_used) for r in rows] == [("wikidata", 0)]
        assert contacts_of(session, company.id) == []

    def test_目录未命中回落计量路径(self, session, company, queue):
        finder = FakeFinder(
            FinderResult(domain="brooklynapparel.com", domain_company_name="Brooklyn Apparel LLC",
                         domain_country="US", contacts=(FoundContact(email="f@x.com"),))
        )
        directory = FakeDirectory(None)
        queue.enqueue("find_contacts", {"company_id": company.id})
        handler = make_find_contacts_handler(finder, CFG, directory=directory)
        Worker(queue, {"find_contacts": handler}).run_once(NOW)
        assert finder.calls == [""]  # 无官网：计量发现按公司名（domain 传空）
        session.expire_all()
        refreshed = session.get(CompanyORM, company.id)
        assert refreshed.website_confirmed is True
        assert refreshed.website_source == "finder"  # 计量路径写的，不是目录


class TestAI提取集成:
    """AI 增强提取：爬虫级合并去重 + handler 级装配（key/日上限/审计）。"""

    def test_无key不装配AI工厂(self, session, company, queue, monkeypatch):
        import app.infrastructure.ai_extractor as ai_mod

        factory_called = []
        monkeypatch.setattr(ai_mod, "make_ai_extractor", lambda s: factory_called.append(1))

        company.website = "https://x.com"
        company.website_confirmed = True
        session.commit()

        class CrawlerSpy:
            def __init__(self, ai_extractor=None):
                pass

            def crawl(self, url):
                from app.infrastructure.crawler import CrawlResult

                return CrawlResult(pages_fetched=[url], blocked_reason="")

        queue.enqueue("crawl_website", {"company_id": company.id})
        # 显式覆盖 .env 带进来的真实 AI key
        cfg_nokey = Settings(hunter_api_key="", ai_api_key="")
        handler = make_crawl_website_handler(CrawlerSpy(), cfg_nokey)
        Worker(queue, {"crawl_website": handler}).run_once(NOW)
        assert factory_called == []  # 无 key：纯净路径

    def test_有key装配且AI调用入审计(self, session, company, queue, monkeypatch):
        from sqlalchemy import select as sel

        import app.infrastructure.ai_extractor as ai_mod
        from app.infrastructure.orm import EnrichmentCallORM

        class FakeAi:
            calls = 1  # 假设已调用一次

        monkeypatch.setattr(ai_mod, "make_ai_extractor", lambda s: FakeAi())

        company.website = "https://x.com"
        company.website_confirmed = True
        session.commit()

        class CrawlerSpy:
            def __init__(self, ai_extractor=None):
                pass

            def crawl(self, url):
                from app.infrastructure.crawler import CrawlResult

                return CrawlResult(pages_fetched=[url], blocked_reason="")

        cfg = Settings(hunter_api_key="", ai_api_key="k")
        queue.enqueue("crawl_website", {"company_id": company.id})
        handler = make_crawl_website_handler(CrawlerSpy(), cfg)
        Worker(queue, {"crawl_website": handler}).run_once(NOW)
        rows = session.scalars(
            sel(EnrichmentCallORM).where(EnrichmentCallORM.provider == "ai-extract")
        ).all()
        assert len(rows) == 1  # 调用过 AI → 审计一行

    def test_AI日上限耗尽不装配(self, session, company, queue, monkeypatch):
        import app.infrastructure.ai_extractor as ai_mod

        factory_called = []
        monkeypatch.setattr(ai_mod, "make_ai_extractor", lambda s: factory_called.append(1))

        company.website = "https://x.com"
        company.website_confirmed = True
        session.commit()
        SqlEnrichmentLog(session).record("ai-extract", company.id, credits_used=0)
        session.commit()

        class CrawlerSpy:
            def __init__(self, ai_extractor=None):
                pass

            def crawl(self, url):
                from app.infrastructure.crawler import CrawlResult

                return CrawlResult(pages_fetched=[url], blocked_reason="")

        cfg = Settings(hunter_api_key="", ai_api_key="k", ai_daily_cap=1)
        queue.enqueue("crawl_website", {"company_id": company.id})
        handler = make_crawl_website_handler(CrawlerSpy(), cfg)
        Worker(queue, {"crawl_website": handler}).run_once(NOW)
        assert factory_called == []


class TestDeepSeekExtractor:
    def test_请求必须关闭推理模式(self):
        """deepseek-flash 思维链会吃光 max_tokens 致 content 为空，提取必须关 thinking。"""
        from app.infrastructure.ai_extractor import DeepSeekExtractor

        captured: dict = {}

        def fake_fetch(url, payload):
            captured.update(payload)
            return {"choices": [{"message": {"content": "[]"}}]}

        DeepSeekExtractor(api_key="k", fetch=fake_fetch).extract("page", "https://x.com")
        assert captured["thinking"] == {"type": "disabled"}
