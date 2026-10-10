"""CSV 导入器：产品目录、提单归并、幂等、冲突标记、导入后重打分。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import BuyerQueryFilters, SqlBuyerQueries
from app.infrastructure.repositories import SqlProductRepository

AS_OF = date(2026, 10, 9)

PRODUCTS_CSV = """code,name,description,buyer_type,hs_code,audience,note,buyer_keywords,peer_keywords
P-GARMENT,成衣,卖给进口商,importer,620462,importer,成衣税号,APPAREL;CLOTHING,GARMENT FACTORY
P-BOARD,纸板,卖给纸壳厂,factory,480810,factory,税号用纸板不是纸箱,PACKAGING;CARTON,PAPER MILL
"""

BILLS_CSV = """arrival_date,bill_number,consignee_name,consignee_address,consignee_country,shipper_name,shipper_address,shipper_country,origin_country,hs_code,product_description,port,quantity
2026-02-10,BOL-001,BROOKLYN APPAREL LLC,"350 FIFTH AVE, NEW YORK NY 10118, USA",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,CHINA,620462,WOMENS COTTON TROUSERS,NEW YORK,1200
2026-05-20,BOL-002,BROOKLYN APPAREL LLC,"350 FIFTH AVE, NEW YORK NY 10118, USA",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,CHINA,620462,WOMENS COTTON TROUSERS,NEW YORK,900
2026-09-01,BOL-003,BROOKLYN APPAREL LLC,"350 FIFTH AVE, NEW YORK NY 10118, USA",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,VIETNAM,620462,WOMENS COTTON TROUSERS,NEW YORK,1500
2025-03-15,BOL-010,LONE STAR CLOTHING CO,"900 RIVER RD, AUSTIN TX 78701, USA",US,NINGBO WEAR CO LTD,"NINGBO, CN",CN,CHINA,620462,WOMENS TROUSERS,HOUSTON,600
2026-03-01,BOL-020,TO THE ORDER OF WELLS FARGER,"",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,CHINA,620462,WOMENS COTTON TROUSERS,NEW YORK,800
2026-03-02,BOL-021,FIRST NATIONAL BANK OF OMAHA,"",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,CHINA,620462,WOMENS COTTON TROUSERS,NEW YORK,100
2026-01-05,BOL-030,GREAT LAKES PACKAGING CORP,"55 INDUSTRIAL PKWY, TOLEDO OH 43604, USA",US,SHANDONG PAPER CO LTD,"JINAN, CN",CN,CHINA,480810,CORRUGATED PAPERBOARD ROLLS,SAVANNAH,20000
2026-04-09,BOL-031,GREAT LAKES PACKAGING CORP,"55 INDUSTRIAL PKWY, TOLEDO OH 43604, USA",US,SHANDONG PAPER CO LTD,"JINAN, CN",CN,CHINA,480810,CORRUGATED PAPERBOARD ROLLS,SAVANNAH,18000
2026-07-20,BOL-032,GREAT LAKES PACKAGING CORP,"55 INDUSTRIAL PKWY, TOLEDO OH 43604, USA",US,SHANDONG PAPER CO LTD,"JINAN, CN",CN,CHINA,480810,CORRUGATED PAPERBOARD ROLLS,SAVANNAH,21000
2026-03-03,BOL-040,MYSTERY BUYERS LLC,"",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,CHINA,6204X2,WOMENS TROUSERS,NEW YORK,300
2025-06-01,BOL-050,UNION PACKAGING CORP,"100 HARBOR WAY, LONG BEACH CA 90802, USA",US,SHANDONG PAPER CO LTD,"JINAN, CN",CN,CHINA,480810,PAPERBOARD,LOS ANGELES,5000
2026-02-11,BOL-051,UNION PACKAGING LLC,"88 BISCAYNE BLVD, MIAMI FL 33132, USA",US,SHANDONG PAPER CO LTD,"JINAN, CN",CN,CHINA,480810,PAPERBOARD,MIAMI,4000
2024-05-01,BOL-060,ANCIENT TRADING CO,"",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,CHINA,620462,WOMENS TROUSERS,NEW YORK,700
"""

GARMENT_ID = 1
BOARD_ID = 2


def seed(session) -> CsvImporter:
    importer = CsvImporter(session)
    importer.import_products(PRODUCTS_CSV)
    return importer


class Test产品导入:
    def test_导入两个示例产品(self, session):
        summary = CsvImporter(session).import_products(PRODUCTS_CSV)
        assert summary.products_upserted == 2
        products = SqlProductRepository(session).list_products()
        assert [p.code for p in products] == ["P-GARMENT", "P-BOARD"]
        board = products[1]
        assert board.buyer_type == "factory"
        assert board.hs_assignments[0].hs_code == "480810"
        assert "纸箱" in board.hs_assignments[0].note

    def test_重复导入产品替换税号对应不累积(self, session):
        seed(session)
        modified = PRODUCTS_CSV + (
            "P-GARMENT,女士棉质长裤（成衣）,卖给海外进口商,importer,620520,importer,第二税号,APPAREL,GARMENT FACTORY\n"
        )
        CsvImporter(session).import_products(modified)
        products = {p.code: p for p in SqlProductRepository(session).list_products()}
        assert len(products["P-GARMENT"].hs_assignments) == 2
        assert session.execute(
            text("SELECT count(*) FROM product_hs_codes")
        ).scalar_one() == 3


class Test提单导入与重打分:
    def test_导入提单后自动重打分(self, session):
        importer = seed(session)
        summary, rescores = importer.import_bills(BILLS_CSV, "test.csv", as_of=AS_OF)
        assert summary.inserted_bills == 13
        assert summary.companies_created > 0
        by_code = {r.product_code: r for r in rescores}
        garment = by_code["P-GARMENT"]
        # Brooklyn=precise, LoneStar=potential, 空抬头/银行/误码=excluded；旧票/MX 不可见
        assert garment.precise == 1
        assert garment.potential == 1
        assert garment.excluded == 3
        board = by_code["P-BOARD"]
        assert board.precise == 1  # GREAT LAKES
        assert board.potential >= 1  # UNION PACKAGING（同名冲突标记对象）

    def test_二次导入全部去重(self, session):
        importer = seed(session)
        importer.import_bills(BILLS_CSV, "test.csv", as_of=AS_OF)
        summary2, _ = importer.import_bills(BILLS_CSV, "test.csv", as_of=AS_OF)
        assert summary2.inserted_bills == 0
        assert summary2.duplicate_bills == 13
        count = session.execute(
            text("SELECT count(*) FROM raw_bills")
        ).scalar_one()
        assert count == 13

    def test_同名不同城市被标记冲突(self, session):
        importer = seed(session)
        importer.import_bills(BILLS_CSV, "test.csv", as_of=AS_OF)
        row = session.execute(
            text(
                "SELECT same_name_conflict FROM companies WHERE normalized_name = 'UNION PACKAGING'"
            )
        ).scalar_one()
        assert row is True

    def test_供货方企业也入库且带国家(self, session):
        importer = seed(session)
        importer.import_bills(BILLS_CSV, "test.csv", as_of=AS_OF)
        row = session.execute(
            text(
                "SELECT country FROM companies WHERE normalized_name = 'HANGZHOU GARMENT'"
            )
        ).scalar_one()
        assert row == "CN"


class Test买家查询与全文检索:
    def seeded_with_scores(self, session):
        importer = seed(session)
        importer.import_bills(BILLS_CSV, "test.csv", as_of=AS_OF)
        return SqlBuyerQueries(session)

    def test_按tier筛选精准客户(self, session):
        queries = self.seeded_with_scores(session)
        items, total = queries.query_buyers(
            BuyerQueryFilters(product_id=GARMENT_ID, audience="importer", tier="precise")
        )
        assert total == 1 and items[0].name == "BROOKLYN APPAREL LLC"
        assert items[0].shipments == 3
        assert items[0].suppliers == ["HANGZHOU GARMENT CO LTD"]
        assert items[0].last_arrival == date(2026, 9, 1)
        assert any(r["code"] == "SUPPLIER_MATCH" for r in items[0].reasons)

    def test_全文检索按词命中(self, session):
        queries = self.seeded_with_scores(session)
        items, _ = queries.query_buyers(
            BuyerQueryFilters(product_id=BOARD_ID, audience="factory", q="packaging")
        )
        names = [i.name for i in items]
        assert "GREAT LAKES PACKAGING CORP" in names
        assert "BROOKLYN APPAREL LLC" not in names

    def test_全文检索支持websearch语法(self, session):
        queries = self.seeded_with_scores(session)
        items, _ = queries.query_buyers(
            BuyerQueryFilters(product_id=GARMENT_ID, audience="importer", q="apparel OR clothing")
        )
        assert any(i.normalized_name == "BROOKLYN APPAREL" for i in items)

    def test_min_shipments过滤(self, session):
        queries = self.seeded_with_scores(session)
        _, total = queries.query_buyers(
            BuyerQueryFilters(product_id=GARMENT_ID, audience="importer", min_shipments=3)
        )
        assert total == 1

    def test_排除tier能查到排除原因(self, session):
        queries = self.seeded_with_scores(session)
        items, _ = queries.query_buyers(
            BuyerQueryFilters(product_id=GARMENT_ID, audience="importer", tier="excluded", order="name")
        )
        codes = {i.exclusion_code for i in items}
        assert codes == {"EX_BLANK_CONSIGNEE", "EX_BANK", "EX_HS_INVALID"}
        hs_invalid = [i for i in items if i.exclusion_code == "EX_HS_INVALID"][0]
        assert hs_invalid.reasons[0]["bill_ids"]

    def test_产品列表带tier计数(self, session):
        queries = self.seeded_with_scores(session)
        products = queries.list_products_with_counts()
        garment = [p for p in products if p["code"] == "P-GARMENT"][0]
        assert garment["counts"]["precise"] == 1
        assert garment["counts"]["excluded"] == 3

    def test_公司抽屉带提单与得分理由(self, session):
        queries = self.seeded_with_scores(session)
        company_id = session.execute(
            text(
                "SELECT id FROM companies WHERE normalized_name = 'BROOKLYN APPAREL'"
            )
        ).scalar_one()
        detail = queries.company_detail(company_id, product_id=GARMENT_ID)
        assert detail is not None
        assert detail.company["country"] == "US"
        assert len(detail.bills) == 3
        assert all(b["role"] == "consignee" for b in detail.bills)
        assert detail.scores[0]["tier"] == "precise"
        supplier_reason = [r for r in detail.scores[0]["reasons"] if r["code"] == "SUPPLIER_MATCH"]
        assert supplier_reason and supplier_reason[0]["bill_ids"]


class TestP1缺陷修复:
    def test_同文件完全相同行只入一票并计重复(self, session):
        """同一 CSV 内两行完全相同：inserted==1、duplicate==1，不得抛异常。"""
        row = "2026-02-10,BOL-001,BROOKLYN APPAREL LLC,\"350 FIFTH AVE, NEW YORK NY 10118, USA\",US,HANGZHOU GARMENT CO LTD,\"NO 66 RD, HANGZHOU, CN\",CN,CHINA,620462,WOMENS COTTON TROUSERS,NEW YORK,1200"
        csv_text = (
            "arrival_date,bill_number,consignee_name,consignee_address,consignee_country,"
            "shipper_name,shipper_address,shipper_country,origin_country,hs_code,"
            "product_description,port,quantity\n" + row + "\n" + row + "\n"
        )
        summary, _ = CsvImporter(session).import_bills(csv_text, rescore=False)
        assert summary.inserted_bills == 1
        assert summary.duplicate_bills == 1

    def test_窗口外提单不进入候选池(self, session):
        """load_pool 按 as_of 往前 24 个月过滤；窗外提单（2024-05 的 ANCIENT）不进候选。"""
        from app.infrastructure.repositories import SqlBuyerPoolReader

        importer = CsvImporter(session)
        importer.import_products(PRODUCTS_CSV)
        importer.import_bills(BILLS_CSV, as_of=AS_OF)
        pool = SqlBuyerPoolReader(session).load_pool(["6204"], AS_OF)
        names = {f.normalized_name for f in pool}
        assert "BROOKLYN APPAREL" in "".join(names) or any("BROOKLYN" in n for n in names)
        assert not any("ANCIENT" in n for n in names)

    def test_查重分批行为等价(self, session, monkeypatch):
        """HASH_QUERY_BATCH 调小后，跨批去重行为与单批一致（锁住分批逻辑）。"""
        CsvImporter.HASH_QUERY_BATCH = 3
        try:
            importer = CsvImporter(session)
            importer.import_bills(BILLS_CSV, rescore=False)  # 12 票，跨多批
            summary, _ = importer.import_bills(BILLS_CSV, rescore=False)  # 全部已存在
            assert summary.inserted_bills == 0
            assert summary.duplicate_bills == 13
        finally:
            CsvImporter.HASH_QUERY_BATCH = 50000


class Test导入缓存覆盖既有公司:
    def test_库中既有公司在批内也被缓存(self, session, monkeypatch):
        """二次导入（新提单+既有公司）：公司查询次数 = 公司数而非行数×2。"""
        importer = CsvImporter(session)
        importer.import_bills(BILLS_CSV, rescore=False)
        session.commit()

        calls = {"n": 0}
        orig_scalar = session.scalar

        def counting_scalar(*args, **kwargs):
            calls["n"] += 1
            return orig_scalar(*args, **kwargs)

        monkeypatch.setattr(session, "scalar", counting_scalar)
        more = BILLS_CSV.replace("BOL-001", "BOL-901").replace("BOL-002", "BOL-902")
        summary, _ = importer.import_bills(more, rescore=False)
        assert summary.inserted_bills == 2
        # 两行共享 1 家收货人 + 1 家供货人：缓存生效则各 miss 一次，共 2 次
        assert calls["n"] <= 2, f"既有公司未走缓存，scalar 查询 {calls['n']} 次"
