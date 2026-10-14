"""意向线索受众（lead）：非提单来源入潜在层；提单受众不混入线索；永不升精准。"""

from dataclasses import replace
from datetime import date

from app.domain.entities import LeadSource, ProductConfig
from app.domain.scoring import score_company
from app.domain.services import RescoreService

from .builders import AS_OF, GARMENT_PRODUCT, bill, company

AI = LeadSource(kind="ai_discover", label="AI 买家发现", ref="discover_buyers:trousers")
OPP = LeadSource(kind="opportunity", label="已加入跟进（lead）", ref="opportunity:1")


def lead_facts(**kw):
    return replace(company(**kw), lead_sources=(AI,))


class Test意向线索受众:
    def test_无提单有来源入潜在且理由点名来源(self):
        result = score_company(GARMENT_PRODUCT, "lead", lead_facts(), AS_OF)
        assert result is not None and result.tier == "potential" and result.audience == "lead"
        assert [r.code for r in result.reasons] == ["SOURCE_LEAD"]
        assert "AI 买家发现" in result.reasons[0].text
        assert result.shipments == 0

    def test_无提单无来源不入池(self):
        assert score_company(GARMENT_PRODUCT, "lead", company(), AS_OF) is None

    def test_线索永不升精准_即使有旧票(self):
        many_old = tuple(bill(i, date(2023, 1, i)) for i in range(1, 6))
        facts = replace(lead_facts(bills=many_old), lead_sources=(AI, OPP))
        result = score_company(GARMENT_PRODUCT, "lead", facts, AS_OF)
        assert result is not None and result.tier == "potential"
        assert "已加入跟进" in result.reasons[0].text

    def test_有合格提单的线索企业_提单受众仍走提单分层_线索受众仍潜在(self):
        facts = lead_facts(bills=(bill(1, date(2026, 3, 1)),))
        bill_side = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert bill_side is not None and "RECENT_24M" in [r.code for r in bill_side.reasons]
        lead_side = score_company(GARMENT_PRODUCT, "lead", facts, AS_OF)
        assert lead_side is not None and lead_side.tier == "potential"
        assert lead_side.reasons[0].code == "SOURCE_LEAD"

    def test_提单受众不因线索单独入池(self):
        # 无合格提单时，importer 视角不该因线索冒充「潜在客户」
        assert score_company(GARMENT_PRODUCT, "importer", lead_facts(), AS_OF) is None

    def test_银行抬头仍排除(self):
        result = score_company(
            GARMENT_PRODUCT, "lead", lead_facts(name="BANK OF AMERICA NA"), AS_OF
        )
        assert result is not None and result.exclusion_code == "EX_BANK"

    def test_货代与空抬头仍排除(self):
        fwd = score_company(
            GARMENT_PRODUCT,
            "lead",
            lead_facts(name="ACME LOGISTICS FREIGHT FORWARDING"),
            AS_OF,
        )
        assert fwd is not None and fwd.exclusion_code == "EX_FORWARDER"
        blank = score_company(
            GARMENT_PRODUCT, "lead", lead_facts(name="TO THE ORDER OF"), AS_OF
        )
        assert blank is not None and blank.exclusion_code == "EX_BLANK_CONSIGNEE"

    def test_产品无税号时提单受众空_线索受众仍可出(self):
        product = ProductConfig(product_id=9, code="P-X", name="新品", buyer_type="factory")
        assert score_company(product, "factory", lead_facts(), AS_OF) is None
        result = score_company(product, "lead", lead_facts(), AS_OF)
        assert result is not None and result.tier == "potential"


class _Pool:
    def __init__(self, facts):
        self.facts = facts
        self.calls: list[tuple] = []

    def load_pool(self, families, as_of, product_id):
        self.calls.append((tuple(families), product_id))
        return self.facts


class _Products:
    def __init__(self, p):
        self.p = p

    def list_products(self):
        return [self.p]

    def get_product(self, pid):
        return self.p


class _Scores:
    results: list = []

    def replace_scores(self, product_id, results):
        self.results = list(results)
        return len(results)


def test_服务层_始终打意向线索受众且与买家类型并排():
    product = ProductConfig(product_id=9, code="P-X", name="新品", buyer_type="both")
    pool, scores = _Pool([lead_facts()]), _Scores()
    summary = RescoreService(products=_Products(product), pool=pool, scores=scores).rescore_product(
        9, AS_OF
    )
    assert pool.calls == [((), 9)]
    # both → importer+factory 无线索提单结果；lead 出 1 条潜在
    assert summary is not None and summary.potential == 1 and summary.precise == 0
    assert set(summary.audiences) == {"factory", "importer", "lead"}
    assert {r.audience for r in scores.results} == {"lead"}
