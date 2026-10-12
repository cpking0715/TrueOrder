"""税号发现：按品名关键词反查 + AI 自动推荐。

「不知道税号怎么办」的两条产品内答案：
- 反查：已导入提单里同行出口同类产品的税号分布
- 自动推荐：填品名即可，AI 直接推断 HS 码并与库内提单交叉验证
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.orm import RawBillORM
from app.interface.deps import get_session

router = APIRouter(prefix="/api/hs", tags=["hs"])


class HsSuggestOut(BaseModel):
    hs_code: str
    shipments: int
    sample_description: str


class HsAutoIn(BaseModel):
    name: str


class HsAutoOut(BaseModel):
    hs_code: str
    source: str  # ai | ai+confirmed
    bill_count: int  # 库内提单交叉验证票数（0=无验证数据）


_HS_AUTO_PROMPT = (
    "根据产品名推断 6 位国际通用 HS 编码（前 6 位即可，不要 10 位国内码）。"
    "只输出 6 位数字，不要任何解释。如果完全无法判断，输出 UNKNOWN。\n产品名：{name}"
)


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


@router.post("/auto", response_model=HsAutoOut)
def auto_hs(
    payload: HsAutoIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """品名 → AI 推断 HS 码 + 库内提单交叉验证（bill_count>0 则 confirmed）。"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="产品名不能为空")

    if not settings.ai_api_key:
        raise HTTPException(status_code=422, detail="未配置 AI Key，无法自动推荐")

    response = httpx.post(
        f"{settings.ai_base_url.rstrip('/')}/chat/completions",
        json={
            "model": settings.ai_model,
            "messages": [
                {"role": "user", "content": _HS_AUTO_PROMPT.format(name=name)},
            ],
            "temperature": 0,
            "max_tokens": 2000,  # 推理模型思维链 ~350 tokens，答案需余量
        },
        headers={"Authorization": f"Bearer {settings.ai_api_key}"},
        timeout=15,
    )
    response.raise_for_status()
    content = (
        response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    )
    digits = "".join(c for c in content if c.isdigit())
    if len(digits) < 6 or digits == "UNKNOWN":
        raise HTTPException(status_code=422, detail=f"AI 无法从「{name}」推断税号，请手动填写")

    hs_code = digits[:6]

    # 交叉验证：库内有没有这个码的提单
    bill_count = int(
        session.scalar(
            select(func.count()).select_from(RawBillORM).where(
                RawBillORM.hs_code == hs_code
            )
        ) or 0
    )
    return HsAutoOut(
        hs_code=hs_code,
        source="ai+confirmed" if bill_count > 0 else "ai",
        bill_count=bill_count,
    )
