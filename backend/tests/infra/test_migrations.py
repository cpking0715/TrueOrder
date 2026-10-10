"""Alembic 迁移：空库 upgrade 建齐表与约束；create_all 旧库可无损接管。"""

from __future__ import annotations

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect, text

from alembic import command

ADMIN_URL = "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"
MIG_DB = "trueorder_mig_test"
MIG_URL = f"postgresql+psycopg://trueorder:trueorder@localhost:5433/{MIG_DB}"
ALEMBIC_INI = "alembic.ini"

BUSINESS_TABLES = {"companies", "company_scores", "product_hs_codes", "products", "raw_bills"}
BUSINESS_UNIQUE = {
    "products_code_key",
    "uq_company_name_country",
    "uq_product_hs_audience",
    "uq_raw_bills_hash",
    "uq_scores_product_company",
}


def _fresh_db() -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {MIG_DB}"))
    admin.dispose()


def _cfg() -> AlembicConfig:
    cfg = AlembicConfig(ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", MIG_URL)
    return cfg


def _business_unique_constraints() -> set[str]:
    engine = create_engine(MIG_URL)
    try:
        inspector = inspect(engine)
        names: set[str] = set()
        with engine.connect() as conn:
            for table in BUSINESS_TABLES:
                for con in inspector.get_unique_constraints(table):
                    names.add(con["name"])
        # products.code 的唯一来自 Column(unique=True)，落在唯一索引里
        with engine.connect() as conn:
            idx = conn.execute(
                text(
                    "select indexname from pg_indexes "
                    "where schemaname='public' and indexname='products_code_key'"
                )
            ).scalars().all()
            names.update(idx)
        return names
    finally:
        engine.dispose()


@pytest.fixture()
def mig_db():
    _fresh_db()
    yield
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)"))
    admin.dispose()


class Test迁移:
    def test_空库升级建齐表与约束并写版本(self, mig_db):
        command.upgrade(_cfg(), "head")
        engine = create_engine(MIG_URL)
        try:
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            with engine.connect() as conn:
                version = conn.execute(text("select version_num from alembic_version")).scalar_one()
        finally:
            engine.dispose()
        assert BUSINESS_TABLES <= tables
        assert version
        assert BUSINESS_UNIQUE <= _business_unique_constraints()

    def test_迁移后ORM建表为空操作(self, mig_db):
        """迁移建的 schema 与 ORM 元数据一致：create_all 不产生新表。"""
        from app.infrastructure.orm import Base

        command.upgrade(_cfg(), "head")
        engine = create_engine(MIG_URL)
        try:
            Base.metadata.create_all(engine)  # 已存在的表会被跳过
            after = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert after == BUSINESS_TABLES | {"alembic_version"}

    def test_create_all旧库stamp后可接管(self, mig_db):
        """create_all 时代的库：stamp head 后再 upgrade 不报错、表不重建。"""
        from app.infrastructure.orm import Base

        engine = create_engine(MIG_URL)
        Base.metadata.create_all(engine)
        engine.dispose()
        command.stamp(_cfg(), "head")
        command.upgrade(_cfg(), "head")  # 已在 head，幂等
        engine = create_engine(MIG_URL)
        try:
            tables = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert BUSINESS_TABLES <= tables
