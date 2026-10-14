"""来源线索入池：AI 发现/商机企业即使无该税号提单也进打分池并落潜在层。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import Settings
from app.domain.entities import DiscoveredBuyer
from app.infrastructure import discover as discover_mod
from app.infrastructure.importers import CsvImporter
from app.infrastructure.orm import (
    CompanyLeadSourceORM,
    CompanyORM,
    CompanyScoreORM,
    OpportunityORM,
    ProductORM,
)
from app.infrastructure.repositories import SqlBuyerPoolReader
from tests.infra.test_queries import AS_OF, BILLS_CSV, PRODUCTS_CSV


def _setup(session) -> tuple[int, int]:
    importer = CsvImporter(session)
    importer.import_products(PRODUCTS_CSV)
    importer.import_bills(BILLS_CSV, as_of=AS_OF, rescore=False)
    pid = session.scalar(select(ProductORM.id))
    c = CompanyORM(
        normalized_name="ACME HOME GOODS", country="US", name_variants=["ACME HOME GOODS INC"]
    )
    session.add(c)
    session.flush()
    return pid, c.id


def _score(session, pid, cid, audience: str = "lead"):
    return session.scalar(
        select(CompanyScoreORM).where(
            CompanyScoreORM.product_id == pid,
            CompanyScoreORM.company_id == cid,
            CompanyScoreORM.audience == audience,
        )
    )


def test_无提单企业不在池_加发现线索后入池并落潜在(session):
    pid, cid = _setup(session)
    reader = SqlBuyerPoolReader(session)
    assert cid not in {f.company_id for f in reader.load_pool(["6204"], AS_OF, pid)}
    session.add(CompanyLeadSourceORM(product_id=pid, company_id=cid, source="ai_discover"))
    session.flush()
    facts = {f.company_id: f for f in reader.load_pool(["6204"], AS_OF, pid)}
    assert facts[cid].bills == () and facts[cid].lead_sources[0].kind == "ai_discover"
    # 无税号族时也照样带出线索企业
    assert cid in {f.company_id for f in reader.load_pool([], AS_OF, pid)}

    CsvImporter(session).rescore_one(pid, AS_OF)
    row = _score(session, pid, cid)
    assert row is not None and row.tier == "potential"
    assert row.reasons[0]["code"] == "SOURCE_LEAD"


def test_商机为线索_流失商机不算(session):
    pid, cid = _setup(session)
    opp = OpportunityORM(product_id=pid, company_id=cid)
    session.add(opp)
    session.flush()
    CsvImporter(session).rescore_one(pid, AS_OF)
    assert _score(session, pid, cid, "lead").tier == "potential"
    assert _score(session, pid, cid, "importer") is None
    opp.stage = "lost"
    session.flush()
    CsvImporter(session).rescore_one(pid, AS_OF)
    assert _score(session, pid, cid) is None


def test_线索只作用于对应产品(session):
    pid, cid = _setup(session)
    session.add(CompanyLeadSourceORM(product_id=pid, company_id=cid, source="ai_discover"))
    session.flush()
    other = SqlBuyerPoolReader(session).load_pool(["6204"], AS_OF, pid + 999)
    assert cid not in {f.company_id for f in other}


def test_发现处理器记录线索并立即重打分(session, monkeypatch):
    pid, existing_id = _setup(session)
    monkeypatch.setattr(
        discover_mod,
        "batch_discover",
        lambda *a, **k: [
            DiscoveredBuyer(company_name="ACME HOME GOODS INC", country="US"),
            DiscoveredBuyer(company_name="NEW WAVE TEXTILES LLC", country="US"),
        ],
    )
    handler = discover_mod.make_discover_buyers_handler(
        Settings(ai_api_key="test", ai_daily_cap=50)
    )
    handler(session, {"product_id": pid, "category": "trousers", "hs_code": "620462"})
    handler(session, {"product_id": pid, "category": "trousers", "hs_code": "620462"})  # 幂等
    leads = session.scalars(
        select(CompanyLeadSourceORM).where(CompanyLeadSourceORM.product_id == pid)
    ).all()
    assert len(leads) == 2 and existing_id in {lead.company_id for lead in leads}
    assert _score(session, pid, existing_id).tier == "potential"


# ---------- 联系人来源线索 ----------
from app.infrastructure.contact_repository import SqlContactRepository  # noqa: E402
from app.infrastructure.lead_sources import (  # noqa: E402
    backfill_contact_leads,
    record_contact_leads,
)
from app.infrastructure.orm import ContactORM  # noqa: E402


def _lead_kinds(session, pid, cid) -> set[str]:
    return set(
        session.scalars(
            select(CompanyLeadSourceORM.source).where(
                CompanyLeadSourceORM.product_id == pid, CompanyLeadSourceORM.company_id == cid
            )
        )
    )


def _add_contact(session, cid, source, email):
    SqlContactRepository(session).add(
        cid, name="X", title="", email=email, phone=None, source=source, source_ref=f"t:{source}"
    )


def test_有产品上下文按联系人来源记线索_无上下文不记(session):
    pid, cid = _setup(session)
    _add_contact(session, cid, "website", "a@acme.example")
    _add_contact(session, cid, "finder", "b@acme.example")
    _add_contact(session, cid, "manual", "c@acme.example")
    _add_contact(session, cid, "csv", "d@acme.example")
    assert record_contact_leads(session, None, cid) == 0
    assert _lead_kinds(session, pid, cid) == set()
    assert record_contact_leads(session, pid, cid) == 3
    assert record_contact_leads(session, pid, cid) == 0  # 幂等
    assert _lead_kinds(session, pid, cid) == {
        "contact_website",
        "contact_hunter",
        "contact_manual",
    }
    CsvImporter(session).rescore_one(pid, AS_OF)
    row = _score(session, pid, cid)
    assert row is not None and row.tier == "potential"
    assert "官网抓取联系人" in row.reasons[0]["text"]


def test_补全处理器包装_带product_id才记线索(session):
    from app.infrastructure.enrichment import with_contact_leads

    pid, cid = _setup(session)

    def fake_crawl(s, payload):
        _add_contact(s, payload["company_id"], "website", "w@acme.example")

    with_contact_leads(fake_crawl)(session, {"company_id": cid})
    assert _lead_kinds(session, pid, cid) == set()
    with_contact_leads(fake_crawl)(session, {"company_id": cid, "product_id": pid})
    assert _lead_kinds(session, pid, cid) == {"contact_website"}


def test_回填_商机与唯一得分产品可推出_多产品歧义跳过(session):
    pid, cid = _setup(session)
    importer = CsvImporter(session)
    other_pid_csv = PRODUCTS_CSV.replace("P-GARMENT,成衣", "P-OTHER,别品")
    importer.import_products(other_pid_csv)
    session.flush()
    pids = list(session.scalars(select(ProductORM.id).order_by(ProductORM.id)))
    p1, p2 = pids[0], pids[-1]
    # A：有商机 → 记到商机产品
    _add_contact(session, cid, "manual", "m@acme.example")
    session.add(OpportunityORM(product_id=p2, company_id=cid))
    # B：只在一个产品有得分 → 记到该产品
    b = CompanyORM(normalized_name="BETA SHOP", country="US", name_variants=["BETA SHOP"])
    # C：两个产品都有得分、无商机 → 歧义跳过
    c = CompanyORM(normalized_name="GAMMA STUDIO", country="US", name_variants=["GAMMA STUDIO"])
    session.add_all([b, c])
    session.flush()
    _add_contact(session, b.id, "finder", "b@beta.example")
    _add_contact(session, c.id, "website", "c@gamma.example")
    for pid_, cid_ in ((p1, b.id), (p1, c.id), (p2, c.id)):
        session.add(
            CompanyScoreORM(product_id=pid_, company_id=cid_, audience="importer", tier="potential")
        )
    session.flush()
    stats = backfill_contact_leads(session.connection())
    assert stats["inserted"] == 2
    assert stats["companies_without_context"] == 1
    assert _lead_kinds(session, p2, cid) == {"contact_manual"}
    assert _lead_kinds(session, p1, cid) == set()
    assert _lead_kinds(session, p1, b.id) == {"contact_hunter"}
    assert _lead_kinds(session, p1, c.id) == set() and _lead_kinds(session, p2, c.id) == set()
    assert backfill_contact_leads(session.connection())["inserted"] == 0
    assert session.scalar(select(ContactORM.id).where(ContactORM.company_id == c.id))
