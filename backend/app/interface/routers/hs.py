"""税号反查：按品名关键词从已导入提单聚合真实使用的税号分布。

「不知道税号怎么办」的产品内答案：同行出口同类产品的提单里，税号是现成的。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from app.infrastructure.orm import RawBillORM
from app.interface.deps import get_session

router = APIRouter(prefix="/api/hs", tags=["hs"])


class HsSuggestOut(BaseModel):
    hs_code: str
    shipments: int
    sample_description: str


@router.get("/suggest", response_model=list[HsSuggestOut])
def suggest_hs(
    q: str = Query(min_length=2),
    limit: int = Query(default=8, ge=1, le=20),
    session: Session = Depends(get_session),
):
    keyword = q.strip()
    if len(keyword) < 2:
        raise HTTPException(status_code=422, detail="关键词至少 2 个字符")
    rows = session.execute(
        select(
            RawBillORM.hs_code,
            func.count().label("shipments"),
            func.max(RawBillORM.product_description).label("sample"),
        )
        .where(
            RawBillORM.product_description.ilike(f"%{keyword}%"),
            RawBillORM.hs_code.isnot(None),
            RawBillORM.hs_code != "",
        )
        .group_by(RawBillORM.hs_code)
        .order_by(literal("shipments").desc())
        .limit(limit)
    ).all()
    return [
        HsSuggestOut(
            hs_code=hs,
            shipments=int(n),
            sample_description=(sample or "")[:120],
        )
        for hs, n, sample in rows
    ]
