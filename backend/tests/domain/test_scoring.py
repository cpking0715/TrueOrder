"""打分规则：潜在/精准分层与六类排除。全部纯函数，as_of 固定，零 mock。"""

from datetime import date

from app.domain.entities import HsAssignment, ProductConfig
from app.domain.scoring import score_company

from .builders import AS_OF, BOARD_PRODUCT, GARMENT_PRODUCT, bill, company


def codes(result_codes):
    return [r.code for r in result_codes]


class Test潜在客户:
    def test_近24个月中国原产一票即为潜在(self):
        facts = company(bills=(bill(1, date(2025, 3, 1)),))
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "potential"
        assert result.exclusion_code is None
        recent = [r for r in result.reasons if r.code == "RECENT_24M"]
        assert recent and recent[0].bill_ids == (1,)
        assert "1" in recent[0].text

    def test_越南原产同样入池(self):
        facts = company(bills=(bill(2, date(2026, 1, 15), origin="VN"),))
        assert score_company(GARMENT_PRODUCT, "importer", facts, AS_OF).tier == "potential"

    def test_恰好24个月边界算在池内(self):
        facts = company(bills=(bill(3, date(2024, 10, 9)),))
        assert score_company(GARMENT_PRODUCT, "importer", facts, AS_OF).tier == "potential"

    def test_超过24个月不入池返回None(self):
        facts = company(bills=(bill(4, date(2024, 8, 31)),))
        assert score_company(GARMENT_PRODUCT, "importer", facts, AS_OF) is None

    def test_非中国越南原产不入池(self):
        facts = company(bills=(bill(5, date(2026, 5, 1), origin="MX"),))
        assert score_company(GARMENT_PRODUCT, "importer", facts, AS_OF) is None

    def test_可疑税号的票不计入(self):
        facts = company(
            bills=(
                bill(6, date(2026, 1, 1)),
                bill(7, date(2026, 2, 1), suspect=True, hs="6204X2"),
            )
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "potential"
        recent = [r for r in result.reasons if r.code == "RECENT_24M"][0]
        assert 7 not in recent.bill_ids

    def test_税号前6位必须与产品一致(self):
        facts = company(bills=(bill(8, date(2026, 3, 1), hs="620442"),))
        assert score_company(GARMENT_PRODUCT, "importer", facts, AS_OF) is None


class Test精准客户:
    def make_repeat_buyer(self):
        return company(
            name="BROOKLYN APPAREL LLC",
            bills=(
                bill(11, date(2026, 2, 10)),
                bill(12, date(2026, 5, 20)),
                bill(13, date(2026, 9, 1)),
            ),
        )

    def test_12个月重复加稳定供货方加业务匹配为精准(self):
        result = score_company(GARMENT_PRODUCT, "importer", self.make_repeat_buyer(), AS_OF)
        assert result.tier == "precise"
        assert set(codes(result.reasons)) >= {
            "RECENT_24M", "REPEAT_12M", "SUPPLIER_MATCH", "BUSINESS_MATCH",
        }
        supplier = [r for r in result.reasons if r.code == "SUPPLIER_MATCH"][0]
        assert "HANGZHOU GARMENT" in supplier.text.upper()
        assert supplier.bill_ids
        # 聚合字段：票数、最近日期、供货方名单
        assert result.shipments == 3
        assert result.last_arrival == date(2026, 9, 1)
        assert result.suppliers == ("HANGZHOU GARMENT CO LTD",)

    def test_只有一票时停在潜在(self):
        facts = company(bills=(bill(21, date(2026, 4, 1)),))
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "potential"
        unmet = [r for r in result.reasons if r.code == "PRECISE_UNMET"]
        assert unmet and "重复" in unmet[0].text

    def test_12个月内轮换供货方不算精准(self):
        facts = company(
            bills=(
                bill(31, date(2026, 2, 1), shipper="AAA GARMENT CO LTD"),
                bill(32, date(2026, 6, 1), shipper="BBB GARMENT CO LTD"),
            )
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "potential"
        unmet = [r for r in result.reasons if r.code == "PRECISE_UNMET"][0].text
        assert "供货方" in unmet

    def test_重复进口发生在13个月前不算精准(self):
        facts = company(
            bills=(
                bill(41, date(2025, 8, 1)),
                bill(42, date(2026, 9, 1)),
            )
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "potential"

    def test_工厂产品业务词不匹配停在潜在(self):
        facts = company(
            name="ACME TRADING LLC",
            address="100 COMMERCE BLVD, CHICAGO IL 60601, USA",
            bills=(
                bill(51, date(2026, 2, 1), hs="480810",
                     shipper="SHANDONG PAPER CO LTD", description="CORRUGATED PAPERBOARD"),
                bill(52, date(2026, 6, 1), hs="480810",
                     shipper="SHANDONG PAPER CO LTD", description="CORRUGATED PAPERBOARD"),
            ),
        )
        result = score_company(BOARD_PRODUCT, "factory", facts, AS_OF)
        assert result.tier == "potential"
        unmet = [r for r in result.reasons if r.code == "PRECISE_UNMET"][0].text
        assert "业务" in unmet

    def test_工厂产品命中行业词为精准(self):
        facts = company(
            name="GREAT LAKES PACKAGING CORP",
            address="55 INDUSTRIAL PKWY, TOLEDO OH 43604, USA",
            bills=(
                bill(61, date(2026, 1, 5), hs="480810",
                     shipper="SHANDONG PAPER CO LTD", description="CORRUGATED PAPERBOARD IN ROLLS"),
                bill(62, date(2026, 4, 9), hs="480810",
                     shipper="SHANDONG PAPER CO LTD", description="CORRUGATED PAPERBOARD IN ROLLS"),
            ),
        )
        result = score_company(BOARD_PRODUCT, "factory", facts, AS_OF)
        assert result.tier == "precise"

    def test_未配置行业词时跳过业务匹配仍可精准(self):
        product = ProductConfig(
            product_id=99,
            code="P-X",
            name="无词产品",
            buyer_type="importer",
            hs_assignments=(HsAssignment(hs_code="620462", audience="importer"),),
        )
        facts = self.make_repeat_buyer()
        result = score_company(product, "importer", facts, AS_OF)
        assert result.tier == "precise"
        assert "BUSINESS_MATCH_SKIPPED" in codes(result.reasons)


class Test排除规则:
    def test_空抬头_TO_THE_ORDER_被排除(self):
        facts = company(
            name="TO THE ORDER OF WELLS FARGER",
            variants=("TO THE ORDER OF WELLS FARGER",),
            bills=(bill(71, date(2026, 3, 1)),),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "excluded"
        assert result.exclusion_code == "EX_BLANK_CONSIGNEE"
        assert [r for r in result.reasons if r.code == "EX_BLANK_CONSIGNEE"][0].bill_ids == (71,)

    def test_空抬头但存在真实名称变体时不排除(self):
        facts = company(
            name="BROOKLYN APPAREL LLC",
            variants=("BROOKLYN APPAREL LLC", "TO THE ORDER"),
            bills=(bill(72, date(2026, 3, 1)),),
        )
        assert score_company(GARMENT_PRODUCT, "importer", facts, AS_OF).tier != "excluded"

    def test_银行抬头被排除(self):
        facts = company(
            name="FIRST NATIONAL BANK OF OMAHA",
            bills=(bill(73, date(2026, 3, 1)),),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.exclusion_code == "EX_BANK"

    def test_货代被排除(self):
        facts = company(
            name="GLOBAL FREIGHT FORWARDING INC",
            bills=(bill(74, date(2026, 3, 1)),),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.exclusion_code == "EX_FORWARDER"

    def test_名称仅含CARGO不视为货代(self):
        # F6 回归：CARGO 一词过宽（如 CARGO BRANDS 是服装品牌常用词），不单独触发
        facts = company(
            name="CAROLINA CARGO BRANDS LLC",
            address="77 HARBOUR ST, CHARLESTON SC 29401, USA",
            bills=(bill(75, date(2026, 3, 1)),),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.exclusion_code != "EX_FORWARDER"

    def test_集团内部供货_全部票来自自身_被排除(self):
        facts = company(
            name="VN GARMENT JOINT STOCK CO",
            bills=(
                bill(81, date(2026, 2, 1), shipper="VN GARMENT JOINT STOCK CO"),
                bill(82, date(2026, 6, 1), shipper="VN GARMENT JOINT STOCK CO"),
            ),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "excluded"
        assert result.exclusion_code == "EX_RELATED_PARTY"

    def test_集团内部票被忽略但外部票保留(self):
        facts = company(
            name="SAIGON APPAREL JSC",
            bills=(
                bill(91, date(2026, 2, 1), shipper="SAIGON APPAREL JSC"),
                bill(92, date(2026, 5, 1), shipper="HANGZHOU GARMENT CO LTD"),
                bill(93, date(2026, 8, 1), shipper="HANGZHOU GARMENT CO LTD"),
            ),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "precise"
        ignored = [r for r in result.reasons if r.code == "IGNORED_RELATED"][0]
        assert 91 in ignored.bill_ids
        assert 92 not in ignored.bill_ids

    def test_供货方为收货人关联公司_名称包含关系也算集团内部(self):
        facts = company(
            name="ABC GARMENT USA",
            bills=(bill(94, date(2026, 2, 1), shipper="ABC GARMENT VIETNAM COMPANY LIMITED"),),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.exclusion_code == "EX_RELATED_PARTY"

    def test_同行海外公司被排除_理由列出命中词与票号(self):
        facts = company(
            name="SHENZHEN GARMENT FACTORY LTD",
            address="INDUSTRIAL ZONE 3, SHENZHEN, CN",
            country="CN",
            bills=(bill(95, date(2026, 3, 1), shipper="SHENZHEN GARMENT FACTORY"),),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.exclusion_code == "EX_PEER_OVERSEAS"
        reason = [r for r in result.reasons if r.code == "EX_PEER_OVERSEAS"][0]
        assert "GARMENT FACTORY" in reason.text
        assert reason.bill_ids == (95,)

    def test_同行词与买家词同时命中时不排除(self):
        # buyer 词（PACKAGING）与 peer 词（PAPER MILL）互不包含：独立的买家信号
        facts = company(
            name="EURO CARTON PACKAGING TRADING BV",
            bills=(
                bill(96, date(2026, 2, 1), hs="480810",
                     shipper="SHANDONG PAPER CO LTD", description="PAPERBOARD"),
                bill(97, date(2026, 5, 1), hs="480810",
                     shipper="SHANDONG PAPER CO LTD", description="PAPERBOARD"),
            ),
        )
        result = score_company(BOARD_PRODUCT, "factory", facts, AS_OF)
        assert result.tier != "excluded"

    def test_买家词只是同行词的子串时是伪命中仍排除(self):
        # F2 回归：PAPER 是买家词、PAPER MILL 是同行词；纸厂命中 PAPER 属伪命中
        facts = company(
            name="ATLANTA PAPER MILL CORP",
            address="9 MILL RD, ATLANTA GA 30301, USA",
            bills=(
                bill(120, date(2026, 2, 1), hs="480810",
                     shipper="SHANDONG PAPER CO LTD", description="PAPERBOARD"),
                bill(121, date(2026, 5, 1), hs="480810",
                     shipper="SHANDONG PAPER CO LTD", description="PAPERBOARD"),
            ),
        )
        result = score_company(BOARD_PRODUCT, "factory", facts, AS_OF)
        assert result.tier == "excluded"
        assert result.exclusion_code == "EX_PEER_OVERSEAS"

    def test_税号误码_仅有可疑票_被排除且理由带票号(self):
        facts = company(
            name="MYSTERY BUYERS LLC",
            bills=(bill(98, date(2026, 4, 1), hs="6204X2", suspect=True),),
        )
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.tier == "excluded"
        assert result.exclusion_code == "EX_HS_INVALID"
        reason = [r for r in result.reasons if r.code == "EX_HS_INVALID"][0]
        assert reason.bill_ids == (98,)


class Test双受众产品:
    def test_两者都卖的产品按受众分别入池(self):
        both = ProductConfig(
            product_id=3,
            code="P-BOTH",
            name="面料与成衣",
            buyer_type="both",
            hs_assignments=(
                HsAssignment(hs_code="620462", audience="importer"),
                HsAssignment(hs_code="600632", audience="factory"),
            ),
            buyer_keywords=("APPAREL", "WEAVING"),
        )
        fabric_buyer = company(
            name="SAIGON WEAVING MILL JSC",
            bills=(bill(101, date(2026, 3, 1), hs="600632", description="COTTON WOVEN FABRIC"),),
        )
        importer_result = score_company(both, "importer", fabric_buyer, AS_OF)
        factory_result = score_company(both, "factory", fabric_buyer, AS_OF)
        assert importer_result is None
        assert factory_result is not None and factory_result.tier == "potential"

    def test_结果带受众字段(self):
        facts = company(bills=(bill(102, date(2026, 1, 1)),))
        result = score_company(GARMENT_PRODUCT, "importer", facts, AS_OF)
        assert result.audience == "importer"
        assert result.product_id == GARMENT_PRODUCT.product_id
        assert result.company_id == facts.company_id
