"""schema / 约束 / 生成列（数据库层）。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.infrastructure.orm import CompanyORM, CompanyScoreORM, RawBillORM


def test_企业规范化名称加国家唯一(session):
    session.add(
        CompanyORM(normalized_name="ACME", country="US", name_variants=["ACME LLC"],
                   variant_addresses=[""], address_guess="", city_guess="")
    )
    session.commit()
    session.add(
        CompanyORM(normalized_name="ACME", country="US", name_variants=["ACME INC"],
                   variant_addresses=[""], address_guess="", city_guess="")
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_同名不同国家不冲突(session):
    session.add(CompanyORM(normalized_name="ACME", country="US"))
    session.add(CompanyORM(normalized_name="ACME", country="DE"))
    session.commit()
    assert session.query(CompanyORM).count() == 2


def test_提单去重哈希唯一(session):
    session.add(RawBillORM(bill_hash="a" * 32, arrival_date="2026-01-01"))
    session.commit()
    session.add(RawBillORM(bill_hash="a" * 32, arrival_date="2026-02-01"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_得分产品公司受众唯一(session):
    from app.infrastructure.orm import CompanyORM, ProductORM

    session.add(ProductORM(code="P1", name="n", buyer_type="importer"))
    session.add(CompanyORM(normalized_name="X", country="US"))
    session.flush()
    session.add(CompanyScoreORM(product_id=1, company_id=1, audience="importer", tier="potential"))
    session.commit()
    session.add(CompanyScoreORM(product_id=1, company_id=1, audience="importer", tier="precise"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_搜索向量由生成列维护(session):
    session.add(
        CompanyORM(
            normalized_name="BROOKLYN APPAREL",
            country="US",
            name_variants=["Brooklyn Apparel LLC"],
            variant_addresses=["350 Fifth Ave, New York NY 10118"],
            address_guess="350 FIFTH AVE, NEW YORK NY 10118",
            city_guess="NEW YORK",
            search_text="Brooklyn Apparel LLC 350 FIFTH AVE, NEW YORK NY 10118 NEW YORK",
        )
    )
    session.commit()
    vector = session.execute(
        text("SELECT search_vector::text FROM companies WHERE normalized_name = 'BROOKLYN APPAREL'")
    ).scalar_one()
    assert "brooklyn" in vector and "apparel" in vector and "york" in vector


def test_gin索引存在(session):
    sql = "SELECT indexname FROM pg_indexes WHERE tablename='companies'"
    indexes = session.execute(text(sql)).scalars()
    assert "ix_companies_search_vector" in set(indexes)


class Test联系人表约束:
    def _company(self, session, name="ACME TRADING"):
        from sqlalchemy import select

        from app.infrastructure.orm import CompanyORM

        existing = session.scalar(
            select(CompanyORM).where(CompanyORM.normalized_name == name)
        )
        if existing:
            return existing.id
        from app.infrastructure.importers import _refresh_search_text

        company = CompanyORM(normalized_name=name, country="US", name_variants=[name])
        _refresh_search_text(company)
        session.add(company)
        session.flush()
        return company.id

    def test_同公司同邮箱大小写不同也冲突(self, session):
        import pytest
        from sqlalchemy.exc import IntegrityError

        from app.infrastructure.orm import ContactORM

        company_id = self._company(session)
        session.add(ContactORM(company_id=company_id, email="a@b.com", source="manual"))
        session.flush()
        session.add(ContactORM(company_id=company_id, email="A@B.COM", source="csv"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_无邮箱联系人不参与唯一约束(self, session):
        from app.infrastructure.orm import ContactORM

        company_id = self._company(session)
        session.add(ContactORM(company_id=company_id, email=None, name="电话联系人甲"))
        session.add(ContactORM(company_id=company_id, email=None, name="电话联系人乙"))
        session.flush()
        assert session.query(ContactORM).filter_by(company_id=company_id).count() == 2

    def test_不同公司同邮箱不冲突(self, session):
        from app.infrastructure.orm import ContactORM

        a = self._company(session, "AAA TRADING")
        b = self._company(session, "BBB TRADING")
        session.add(ContactORM(company_id=a, email="shared@b.com"))
        session.add(ContactORM(company_id=b, email="shared@b.com"))
        session.flush()

    def test_坏source被CHECK拒绝(self, session):
        import pytest
        from sqlalchemy.exc import IntegrityError

        from app.infrastructure.orm import ContactORM

        company_id = self._company(session)
        session.add(ContactORM(company_id=company_id, email="x@y.com", source="scraped"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_删公司级联删联系人(self, session):
        from app.infrastructure.orm import CompanyORM, ContactORM

        company_id = self._company(session, "CASCADE TRADING")
        session.add(ContactORM(company_id=company_id, email="c@d.com"))
        session.flush()
        session.execute(
            CompanyORM.__table__.delete().where(CompanyORM.id == company_id)
        )
        session.flush()
        assert (
            session.query(ContactORM).filter_by(company_id=company_id).count() == 0
        )
