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
