"""FastAPI 依赖注入：会话与仓储（测试用 dependency_overrides 替换 get_session）。"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.db import make_engine, make_session_factory
from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import SqlBuyerQueries


@lru_cache
def _session_factory():
    engine = make_engine(get_settings().database_url)
    return make_session_factory(engine)


def get_session() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_buyer_queries(session: Session = Depends(get_session)) -> SqlBuyerQueries:
    return SqlBuyerQueries(session)


def get_importer(session: Session = Depends(get_session)) -> CsvImporter:
    return CsvImporter(session)
