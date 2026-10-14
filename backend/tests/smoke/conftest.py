"""e2e 冒烟夹具：真测试库 + TestClient（与接口层同构，走完整 HTTP 链路）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.infrastructure.orm import Base
from app.interface.auth import require_api_token
from app.interface.deps import get_session
from app.interface.main import create_app

ADMIN_URL = "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"
TEST_DB = "trueorder_smoke"
TEST_URL = f"postgresql+psycopg://trueorder:trueorder@localhost:5433/{TEST_DB}"


@pytest.fixture(scope="session")
def engine() -> Engine:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    eng = create_engine(TEST_URL, pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def client(engine: Engine) -> TestClient:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)

    def override_get_session():
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[require_api_token] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session.rollback()
    session.close()
