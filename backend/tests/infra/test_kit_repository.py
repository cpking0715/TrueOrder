"""出海包仓储（真 PostgreSQL）：进度持久化、档案 upsert、50 买家导入幂等、询盘落库、PDF 结构。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from app.domain.kit import ProductProfileInput
from app.infrastructure.kit_repository import SqlKitRepository
from app.infrastructure.kit_sales_repository import SqlKitSalesRepository
from app.infrastructure.orm import CompanyORM, ContactORM, ProductORM
from app.infrastructure.pdf_writer import render_text_pdf

FIXTURE = Path(__file__).parent.parent / "fixtures" / "kit_kidswear_buyers.csv"


def _product(session, code: str = "KIT-1") -> int:
    p = ProductORM(code=code, name="Organic Baby Romper", buyer_type="importer")
    session.add(p)
    session.commit()
    return p.id


def test_任务进度落库并可取消(session):
    repo = SqlKitRepository(session)
    repo.set_done("d1_buyer_type", True)
    repo.set_done("d2_pick_products", True)
    repo.set_done("d2_pick_products", False)
    assert repo.progress() == {"d1_buyer_type": True, "d2_pick_products": False}


def test_产品档案_upsert_与主推计数(session):
    repo = SqlKitRepository(session)
    pid = _product(session)
    prof = ProductProfileInput(
        "https://x.example.com/a.jpg", "cotton", 300, 30, ("GOTS", " "), True
    )
    repo.upsert_profile(pid, prof)
    repo.upsert_profile(pid, prof)
    assert repo.featured_count() == 1
    row = repo.list_profiles()[0]
    assert row.has_profile and row.selling_points == ("GOTS",)


def test_导入50买家_去重_非法邮箱_二次导入0新增(session):
    repo = SqlKitRepository(session)
    text = FIXTURE.read_text(encoding="utf-8")
    first = repo.import_buyers(text, "kit_kidswear_buyers.csv")
    assert first.rows_valid == 50 and first.buyers_tagged == 50
    assert first.duplicates_in_file == 2 and len(first.errors) == 1
    assert first.contacts_added == 50  # 43 个邮箱 + 7 个只有电话
    assert session.scalar(select(func.count()).select_from(CompanyORM)) == 50
    second = repo.import_buyers(text, "kit_kidswear_buyers.csv")
    assert second.buyers_tagged == 0 and second.already_in_library == 50
    assert second.companies_created == 0 and second.contacts_added == 0
    assert session.scalar(select(func.count()).select_from(ContactORM)) == 50
    assert len(repo.list_buyers(country="AE")) == 10
    assert len(repo.list_buyers(channel="whatsapp")) == 10
    whats = repo.list_buyers(channel="whatsapp")[0]
    assert repo.update_buyer_tags(whats.company_id, None, "contacted")
    assert len(repo.list_buyers(stage="contacted")) == 1


def test_询盘落库与状态更新(session):
    repo = SqlKitRepository(session)
    repo.import_buyers(FIXTURE.read_text(encoding="utf-8"), "f.csv")
    pid = _product(session)
    cid = repo.list_buyers()[0].company_id
    sales = SqlKitSalesRepository(session)
    assert sales.create_inquiry(999999, pid, 1, Decimal("1"), "USD", "") is None
    iid = sales.create_inquiry(cid, pid, 500, Decimal("3.25"), "usd", " 要样品 ")
    assert iid is not None
    sales.set_status(iid, "quoted")
    row = sales.get_inquiry(iid)
    assert row is not None and row.status == "quoted" and row.currency == "USD"
    assert row.unit_price == Decimal("3.2500") and row.note == "要样品"


def test_PDF_结构完整且转义括号():
    pdf = render_text_pdf([("PROFORMA INVOICE (PI)", 16), ("中文", 10)])
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert b"PROFORMA INVOICE \\(PI\\)" in pdf and b"(??)" in pdf
    xref_at = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert pdf[xref_at:].startswith(b"xref")
