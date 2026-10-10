"""FastAPI 依赖注入：会话与仓储（测试用 dependency_overrides 替换 get_session）。"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.contact_repository import SqlContactRepository
from app.infrastructure.db import make_engine, make_session_factory
from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import SqlBuyerQueries
from app.infrastructure.repositories import SqlProductRepository


@lru_cache
def _session_factory():
    engine = make_engine(get_settings().database_url)
    return make_session_factory(engine)


def get_session() -> Iterator[Session]:
    """每请求独立会话：请求成功自动提交，异常回滚（写路径统一出口，repo 不再各自 commit）。"""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def get_buyer_queries(session: Session = Depends(get_session)) -> SqlBuyerQueries:
    return SqlBuyerQueries(session)


def get_importer(session: Session = Depends(get_session)) -> CsvImporter:
    return CsvImporter(session)


def get_product_repository(session: Session = Depends(get_session)) -> SqlProductRepository:
    return SqlProductRepository(session)


def get_contact_repository(session: Session = Depends(get_session)) -> SqlContactRepository:
    return SqlContactRepository(session)
