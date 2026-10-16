"""出海包 v0.1（内部工具）：今日任务台、产品档案、买家线索库。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domain.kit import (
    BUYER_CHANNELS,
    BUYER_STAGES,
    KIT_TASKS,
    TASK_KEYS,
    ProductProfileInput,
    can_feature,
    current_day,
    validate_profile,
)
from app.infrastructure.kit_repository import ProfileRow, SqlKitRepository
from app.interface.deps import CsvUpload, get_session, read_csv_upload
from app.interface.schemas_kit import (
    KitBuyerImportOut,
    KitBuyerOut,
    KitBuyerPatchIn,
    KitProfileIn,
    KitProfileOut,
    KitTaskDoneIn,
    KitTaskOut,
    KitTasksOut,
)

router = APIRouter(prefix="/api/kit", tags=["kit"])


def _repo(session: Session = Depends(get_session)) -> SqlKitRepository:
    return SqlKitRepository(session)


# ---------- 今日任务台 ----------


@router.get("/tasks", response_model=KitTasksOut)
def list_tasks(repo: SqlKitRepository = Depends(_repo)):
    done = repo.progress()
    tasks = [
        KitTaskOut(key=t.key, day=t.day, title=t.title, page=t.page, done=done.get(t.key, False))
        for t in KIT_TASKS
    ]
    return KitTasksOut(
        today=current_day(done),
        done_count=sum(1 for t in tasks if t.done),
        total=len(tasks),
        tasks=tasks,
    )


@router.put("/tasks/{task_key}", status_code=204)
def set_task_done(task_key: str, payload: KitTaskDoneIn, repo: SqlKitRepository = Depends(_repo)):
    if task_key not in TASK_KEYS:
        raise HTTPException(status_code=404, detail=f"任务 {task_key} 不存在")
    repo.set_done(task_key, payload.done)


# ---------- 产品档案 ----------


def _profile_out(row: ProfileRow) -> KitProfileOut:
    return KitProfileOut(**{**row.__dict__, "selling_points": list(row.selling_points)})


@router.get("/products", response_model=list[KitProfileOut])
def list_profiles(repo: SqlKitRepository = Depends(_repo)):
    return [_profile_out(r) for r in repo.list_profiles()]


@router.put("/products/{product_id}/profile", response_model=KitProfileOut)
def save_profile(
    product_id: int, payload: KitProfileIn, repo: SqlKitRepository = Depends(_repo)
):
    if not repo.product_exists(product_id):
        raise HTTPException(status_code=404, detail=f"产品 {product_id} 不存在")
    data = ProductProfileInput(
        image_url=payload.image_url,
        specs=payload.specs,
        moq=payload.moq,
        lead_time_days=payload.lead_time_days,
        selling_points=tuple(payload.selling_points),
        featured=payload.featured,
    )
    errors = validate_profile(data)
    if errors:
        raise HTTPException(status_code=422, detail="；".join(errors))
    if data.featured and not can_feature(repo.featured_count(), repo.is_featured(product_id)):
        raise HTTPException(status_code=409, detail="主推款最多 5 个，请先取消一个")
    repo.upsert_profile(product_id, data)
    row = next(r for r in repo.list_profiles() if r.product_id == product_id)
    return _profile_out(row)


# ---------- 买家线索库 ----------


@router.post("/buyers/import", response_model=KitBuyerImportOut)
def import_buyers(
    upload: CsvUpload = Depends(read_csv_upload), repo: SqlKitRepository = Depends(_repo)
):
    """同步导入（50–100 行量级）；只入库与打标签，不触发任何补全或发送。"""
    result = repo.import_buyers(upload.text, upload.filename)
    return KitBuyerImportOut(**result.__dict__)


@router.get("/buyers", response_model=list[KitBuyerOut])
def list_buyers(
    country: str = "", channel: str = "", stage: str = "",
    repo: SqlKitRepository = Depends(_repo),
):
    return [KitBuyerOut(**b.__dict__) for b in repo.list_buyers(country, channel, stage)]


@router.patch("/buyers/{company_id}", status_code=204)
def patch_buyer(
    company_id: int, payload: KitBuyerPatchIn, repo: SqlKitRepository = Depends(_repo)
):
    if payload.channel is not None and payload.channel not in BUYER_CHANNELS:
        raise HTTPException(status_code=422, detail=f"渠道取值不认识：{payload.channel}")
    if payload.stage is not None and payload.stage not in BUYER_STAGES:
        raise HTTPException(status_code=422, detail=f"阶段取值不认识：{payload.stage}")
    if not repo.update_buyer_tags(company_id, payload.channel, payload.stage):
        raise HTTPException(status_code=404, detail=f"买家 {company_id} 不在线索库")
