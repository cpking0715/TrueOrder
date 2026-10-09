"""meta 路由：非全量样本声明。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.interface.schemas import MetaOut

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", response_model=MetaOut)
def meta():
    settings = get_settings()
    return MetaOut(sample_mode=settings.sample_mode, sample_notice=settings.sample_notice)


@router.get("/health")
def health():
    return {"status": "ok"}
