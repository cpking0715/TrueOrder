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

    def test_迁移schema与ORM元数据一致(self, mig_db):
        """升级后的 schema 与 ORM 元数据全量比对（表/列/索引/约束），无漂移。"""
        from alembic.autogenerate import compare_metadata
        from alembic.runtime.migration import MigrationContext

        from app.infrastructure.orm import Base

        command.upgrade(_cfg(), "head")
        engine = create_engine(MIG_URL)
        try:
            with engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                diff = compare_metadata(ctx, Base.metadata)
        finally:
            engine.dispose()
        assert diff == [], f"迁移与 ORM 元数据漂移: {diff}"

    def test_wp0时代旧库stamp后可接管并补齐增量(self, mig_db):
        """create_all 时代（WP0 之前）的库：stamp 基线后 upgrade 补齐 contacts 与官网列。"""
        from app.infrastructure.orm import Base

        engine = create_engine(MIG_URL)
        Base.metadata.create_all(engine)
        with engine.begin() as conn:  # 剥掉 WP1/WP3 新增对象 = 模拟历史版本的库
            conn.execute(text("DROP TABLE email_messages"))
            conn.execute(text("DROP TABLE email_templates"))
            conn.execute(text("DROP TABLE suppressions"))
            conn.execute(text("DROP TABLE activities"))
            conn.execute(text("DROP TABLE opportunities"))
            conn.execute(text("DROP TABLE jobs"))
            conn.execute(text("DROP TABLE enrichment_calls"))
            conn.execute(text("DROP TABLE job_uploads"))
            conn.execute(text("DROP TABLE company_lead_sources"))
            conn.execute(text("ALTER TABLE companies DROP COLUMN website_source"))
            conn.execute(text("ALTER TABLE companies DROP COLUMN website_confidence"))
            conn.execute(text("DROP TABLE contacts"))
            conn.execute(text("ALTER TABLE companies DROP COLUMN website"))
            conn.execute(text("ALTER TABLE companies DROP COLUMN website_confirmed"))
        engine.dispose()
        from app.bootstrap import _ensure_schema

        _ensure_schema(MIG_URL)
        engine = create_engine(MIG_URL)
        try:
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            has_website = any(
                c["name"] == "website"
                for c in inspector.get_columns("companies")
            )
        finally:
            engine.dispose()
        assert BUSINESS_TABLES <= tables
        assert "contacts" in tables, "旧库升级后应补齐 contacts 表"
        assert has_website, "旧库升级后应补齐 companies.website 列"


class Test旧库接管:
    def test_create_all旧库经ensure_schema补齐增量索引(self, mig_db):
        """迁移前旧库（无增量索引）经 bootstrap._ensure_schema 接管后必须补上索引。"""
        from app.bootstrap import _ensure_schema
        from app.infrastructure.orm import Base

        engine = create_engine(MIG_URL)
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            # 剥掉 WP1/WP3 新增对象与表达式索引 = 模拟迁移前的历史库
            conn.execute(text("DROP TABLE email_messages"))
            conn.execute(text("DROP TABLE email_templates"))
            conn.execute(text("DROP TABLE suppressions"))
            conn.execute(text("DROP TABLE activities"))
            conn.execute(text("DROP TABLE opportunities"))
            conn.execute(text("DROP TABLE jobs"))
            conn.execute(text("DROP TABLE enrichment_calls"))
            conn.execute(text("DROP TABLE job_uploads"))
            conn.execute(text("DROP TABLE company_lead_sources"))
            conn.execute(text("ALTER TABLE companies DROP COLUMN website_source"))
            conn.execute(text("ALTER TABLE companies DROP COLUMN website_confidence"))
            conn.execute(text("DROP TABLE contacts"))
            conn.execute(text("ALTER TABLE companies DROP COLUMN website"))
            conn.execute(text("ALTER TABLE companies DROP COLUMN website_confirmed"))
            conn.execute(text("DROP INDEX IF EXISTS ix_raw_bills_hs4_arrival"))
        engine.dispose()

        _ensure_schema(MIG_URL)

        engine = create_engine(MIG_URL)
        try:
            with engine.connect() as conn:
                has_index = conn.execute(
                    text(
                        "select 1 from pg_indexes "
                        "where indexname = 'ix_raw_bills_hs4_arrival'"
                    )
                ).scalar()
        finally:
            engine.dispose()
        assert has_index, "旧库被 stamp 到 head 后增量索引缺失"
