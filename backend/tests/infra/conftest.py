"""基础设施层测试夹具：真 PostgreSQL（Docker 5433），每用例重建 schema。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.infrastructure.orm import Base

ADMIN_URL = "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"
TEST_DB = "trueorder_test"
TEST_URL = f"postgresql+psycopg://trueorder:trueorder@localhost:5433/{TEST_DB}"


@pytest.fixture(scope="session")
def engine() -> Engine:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    eng = create_engine(TEST_URL, pool_pre_ping=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine: Engine) -> Session:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sess = Session(engine)
    yield sess
    sess.rollback()
    sess.close()
