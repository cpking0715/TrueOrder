"""税号发现：按品名关键词反查 + AI 自动推荐。

「不知道税号怎么办」的两条产品内答案：
- 反查：已导入提单里同行出口同类产品的税号分布
- 自动推荐：填品名即可，AI 直接推断 HS 码并与库内提单交叉验证
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.llm_client import AiQuota, LlmClient, LlmError, LlmNotConfigured
from app.infrastructure.queries import SqlBuyerQueries
from app.interface.deps import get_buyer_queries, get_session

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
    "根据产品名推断 6 位国际通用 HS 编码（世界海关组织 HS 前 6 位，不是 10 位国内码）。\n"
    "判定要点：先看品类；再看填充/材质；再看适用人群"
    "（男装/男童服装通常 6201 开头，女装/女童通常 6202 开头，婴儿服装 6209 开头——"
    "这些 4 位只是品类开头，最终答案必须补全到 6 位）。\n"
    "只输出恰好 6 位数字，不要任何解释。如果完全无法判断，输出 UNKNOWN。\n产品名：{name}"
)


@router.get("/suggest", response_model=list[HsSuggestOut])
def suggest_hs(
    q: str = Query(min_length=2),
    limit: int = Query(default=8, ge=1, le=20),
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
):
    keyword = q.strip()
    if len(keyword) < 2:
        raise HTTPException(status_code=422, detail="关键词至少 2 个字符")
    return [
        HsSuggestOut(hs_code=hs, shipments=n, sample_description=sample)
        for hs, n, sample in queries.suggest_hs_codes(keyword, limit)
    ]



@router.post("/auto", response_model=HsAutoOut)
def auto_hs(
    payload: HsAutoIn,
    session: Session = Depends(get_session),
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
    settings: Settings = Depends(get_settings),
):
    """品名 → AI 推断 HS 码 + 库内提单交叉验证（bill_count>0 则 confirmed）。"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="产品名不能为空")

    quota = AiQuota(session, settings.ai_daily_cap)
    if quota.remaining() <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"今日 AI 调用已达上限（{settings.ai_daily_cap}），请明日再试或手动填写",
        )
    try:
        client = LlmClient.from_settings(settings, timeout=15)
    except LlmNotConfigured as exc:
        raise HTTPException(status_code=422, detail="未配置 AI Key，无法自动推荐") from exc

    # thinking 关闭后输出仍偶发漂移（不足 6 位 / UNKNOWN），最多试 3 次；每次外呼计入 AI 日额度
    digits = ""
    try:
        for _ in range(min(3, quota.remaining())):
            quota.record("ai-hs")
            content = client.chat(
                [{"role": "user", "content": _HS_AUTO_PROMPT.format(name=name)}],
                temperature=0,
                max_tokens=2000,
            )
            digits = "".join(c for c in content if c.isdigit())
            if len(digits) >= 6:
                break
    except LlmError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        session.commit()  # 审计行无论成败都落库
    if len(digits) < 6:
        raise HTTPException(status_code=422, detail=f"AI 无法从「{name}」推断税号，请手动填写")

    hs_code = digits[:6]

    # 交叉验证：库内有没有这个码的提单
    bill_count = queries.bill_count_for_hs(hs_code)
    return HsAutoOut(
        hs_code=hs_code,
        source="ai+confirmed" if bill_count > 0 else "ai",
        bill_count=bill_count,
    )
