"""界面查询层：公司抽屉提单上限与截断标记。"""

from __future__ import annotations

from datetime import date

from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import SqlBuyerQueries

AS_OF = date(2026, 10, 9)

PRODUCTS_CSV = """code,name,description,buyer_type,hs_code,audience,note,buyer_keywords,peer_keywords
P-GARMENT,成衣,卖给进口商,importer,620462,importer,成衣税号,APPAREL;CLOTHING,GARMENT FACTORY
"""

BILLS_CSV = """arrival_date,bill_number,consignee_name,consignee_address,consignee_country,shipper_name,shipper_address,shipper_country,origin_country,hs_code,product_description,port,quantity
2026-02-10,BOL-001,BROOKLYN APPAREL LLC,"350 FIFTH AVE, NEW YORK NY 10118, USA",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,CHINA,620462,WOMENS COTTON TROUSERS,NEW YORK,1200
2026-05-20,BOL-002,BROOKLYN APPAREL LLC,"350 FIFTH AVE, NEW YORK NY 10118, USA",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,CHINA,620462,WOMENS COTTON TROUSERS,NEW YORK,900
2026-09-01,BOL-003,BROOKLYN APPAREL LLC,"350 FIFTH AVE, NEW YORK NY 10118, USA",US,HANGZHOU GARMENT CO LTD,"NO 66 RD, HANGZHOU, CN",CN,VIETNAM,620462,WOMENS COTTON TROUSERS,NEW YORK,1500
"""


def _seed(session) -> int:
    importer = CsvImporter(session)
    importer.import_products(PRODUCTS_CSV)
    importer.import_bills(BILLS_CSV, as_of=AS_OF, rescore=False)
    from sqlalchemy import select

    from app.infrastructure.orm import CompanyORM

    return session.scalar(
        select(CompanyORM.id).where(CompanyORM.normalized_name == "BROOKLYN APPAREL")
    )


class Test公司抽屉提单上限:
    def test_超上限标记截断且只返回上限数(self, session):
        company_id = _seed(session)
        assert company_id is not None
        queries = SqlBuyerQueries(session)
        detail = queries.company_detail(company_id, bill_limit=2)
        assert len(detail.bills) == 2
        assert detail.bills_truncated is True
        full = queries.company_detail(company_id, bill_limit=500)
        assert len(full.bills) == 3
        assert full.bills_truncated is False


class Test并发建产品:
    def test_两个并发会话不产生重复编号(self, session, engine):
        """真并发（双线程双 Session）：撞号一方自动换号重试，编号不重复。"""
        from concurrent.futures import ThreadPoolExecutor

        from sqlalchemy import select
        from sqlalchemy.orm import Session as OrmSession

        from app.domain.parse import build_quick_product
        from app.infrastructure.orm import ProductORM
        from app.infrastructure.repositories import SqlProductRepository

        def create(name: str) -> tuple[int, str | None]:
            s = OrmSession(engine)
            try:
                repo = SqlProductRepository(s)
                pid, err = repo.create_quick(
                    lambda code: build_quick_product(
                        code=code, name=name, hs_code="620462", buyer_type="importer"
                    )
                )
                if err is None:
                    s.commit()
                return pid, err
            finally:
                s.rollback()
                s.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            fa = pool.submit(create, "并发A")
            fb = pool.submit(create, "并发B")
            id_a, err_a = fa.result()
            id_b, err_b = fb.result()
        assert err_a is None and err_b is None, (err_a, err_b)
        assert id_a != id_b
        codes = session.scalars(
            select(ProductORM.code).where(ProductORM.id.in_([id_a, id_b]))
        ).all()
        assert len(set(codes)) == 2


class Test分批导出:
    def test_同票数多公司分批遍历不重不漏(self, session):
        from sqlalchemy import select

        from app.infrastructure.orm import ProductORM
        from app.infrastructure.queries import BuyerQueryFilters

        rows = "\n".join(
            f"2026-05-0{i},BOL-X{i},ACME {chr(64 + i)} INC,\"1 ST, NY, USA\",US,"
            f"HANGZHOU GARMENT CO LTD,\"NO 66 RD, HANGZHOU, CN\",CN,CHINA,620462,"
            f"WOMENS COTTON TROUSERS,NEW YORK,100"
            for i in range(1, 8)
        )
        importer = CsvImporter(session)
        importer.import_products(PRODUCTS_CSV)
        importer.import_bills(BILLS_CSV.splitlines()[0] + "\n" + rows + "\n", as_of=AS_OF)
        pid = session.scalar(select(ProductORM.id))
        queries = SqlBuyerQueries(session)
        for order in ("shipments", "last_arrival", "name"):
            f = BuyerQueryFilters(product_id=pid, audience="importer", order=order, limit=10**5)
            _, total = queries.query_buyers(f)
            ids = [b.company_id for b in queries.iter_buyers(f, batch_size=2)]
            assert total >= 7
            assert len(ids) == len(set(ids)) == total, order
