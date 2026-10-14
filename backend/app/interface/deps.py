"""FastAPI 依赖注入：会话与仓储（测试用 dependency_overrides 替换 get_session）。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
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
    """每请求独立会话。提交由写方法在响应前显式完成（避免响应后提交的读写竞态）。"""
    session = _session_factory()()
    try:
        yield session
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


@dataclass(frozen=True)
class CsvUpload:
    text: str
    filename: str


def read_csv_upload(
    file: UploadFile,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> CsvUpload:
    """三个 CSV 导入端点共用：大小上限 413、非法 Content-Length 400、非 UTF-8 422。

    同步依赖（FastAPI 放线程池执行），读取不阻塞事件循环。
    """
    limit = settings.max_upload_mb * 1024 * 1024
    too_large = HTTPException(
        status_code=413, detail=f"文件超过上传上限 {settings.max_upload_mb} MB"
    )
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Content-Length 非法") from exc
        if declared_size > limit:
            raise too_large
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise too_large
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"CSV 必须是 UTF-8：{exc}") from exc
    return CsvUpload(text=text, filename=file.filename or "upload")
