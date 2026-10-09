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
