"""商机路由（WP2）：加入跟进、看板列表、阶段变更、活动、时间线。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.infrastructure.opportunity_repository import (
    SqlOpportunityRepository,
    today_utc,
)
from app.interface.deps import get_session

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


class OpportunityOut(BaseModel):
    opportunity_id: int
    product_id: int
    company_id: int
    company_name: str
    stage: str
    intent: str
    next_follow_up_on: date | None = None
    owner_note: str = ""
    closed_reason: str | None = None


class ActivityOut(BaseModel):
    activity_id: int
    opportunity_id: int
    contact_id: int | None = None
    kind: str
    summary: str
    body: str = ""
    intent_after: str | None = None
    occurred_at: str


class OpportunityCreateIn(BaseModel):
    product_id: int
    company_id: int
    owner_note: str = ""


class OpportunityUpdateIn(BaseModel):
    stage: str | None = None
    closed_reason: str | None = None
    intent: str | None = Field(default=None, pattern="^(cold|warm|hot)$")
    next_follow_up_on: date | None = None
    owner_note: str | None = None


class ActivityCreateIn(BaseModel):
    kind: str = Field(pattern="^(email_out|email_in|call|whatsapp|note)$")
    summary: str
    body: str = ""
    contact_id: int | None = None
    intent_after: str | None = Field(default=None, pattern="^(cold|warm|hot)$")


def _to_out(row) -> OpportunityOut:
    return OpportunityOut(
        opportunity_id=row.opportunity_id,
        product_id=row.product_id,
        company_id=row.company_id,
        company_name=row.company_name,
        stage=row.stage,
        intent=row.intent,
        next_follow_up_on=row.next_follow_up_on,
        owner_note=row.owner_note,
        closed_reason=row.closed_reason,
    )


def _repo(session: Session = Depends(get_session)) -> SqlOpportunityRepository:
    return SqlOpportunityRepository(session)


@router.post("", response_model=OpportunityOut, status_code=201)
def create_opportunity(payload: OpportunityCreateIn, repo=Depends(_repo)):
    """从买家列表「加入跟进」：已存在直接返回既有（幂等）。"""
    row, _created = repo.add(payload.product_id, payload.company_id, payload.owner_note)
    return _to_out(row)


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(
    product_id: int | None = None,
    stage: str | None = None,
    due: str | None = None,
    repo=Depends(_repo),
):
    due_on = today_utc() if due == "today" else None
    return [_to_out(r) for r in repo.list_opportunities(product_id, stage, due_on)]


@router.patch("/{opportunity_id}", response_model=OpportunityOut)
def update_opportunity(opportunity_id: int, payload: OpportunityUpdateIn, repo=Depends(_repo)):
    result = repo.update(
        opportunity_id,
        stage=payload.stage,
        closed_reason=payload.closed_reason,
        intent=payload.intent,
        next_follow_up_on=payload.next_follow_up_on,
        owner_note=payload.owner_note,
    )
    if result == "not_found":
        raise HTTPException(status_code=404, detail=f"商机 {opportunity_id} 不存在")
    if isinstance(result, str):
        raise HTTPException(status_code=422, detail=result)
    return _to_out(result)


@router.post("/{opportunity_id}/activities", response_model=ActivityOut, status_code=201)
def add_activity(opportunity_id: int, payload: ActivityCreateIn, repo=Depends(_repo)):
    result = repo.add_activity(
        opportunity_id,
        kind=payload.kind,
        summary=payload.summary,
        body=payload.body,
        contact_id=payload.contact_id,
        intent_after=payload.intent_after,
    )
    if result == "not_found":
        raise HTTPException(status_code=404, detail=f"商机 {opportunity_id} 不存在")
    if result == "invalid_kind":
        raise HTTPException(status_code=422, detail="活动类型非法")
    return ActivityOut(
        activity_id=result.activity_id,
        opportunity_id=result.opportunity_id,
        contact_id=result.contact_id,
        kind=result.kind,
        summary=result.summary,
        body=result.body,
        intent_after=result.intent_after,
        occurred_at=result.occurred_at.isoformat() if result.occurred_at else "",
    )


@router.get("/{opportunity_id}/timeline", response_model=list[ActivityOut])
def timeline(opportunity_id: int, repo=Depends(_repo)):
    rows = repo.timeline(opportunity_id)
    if rows is None:
        raise HTTPException(status_code=404, detail=f"商机 {opportunity_id} 不存在")
    return [
        ActivityOut(
            activity_id=a.activity_id,
            opportunity_id=a.opportunity_id,
            contact_id=a.contact_id,
            kind=a.kind,
            summary=a.summary,
            body=a.body,
            intent_after=a.intent_after,
            occurred_at=a.occurred_at.isoformat() if a.occurred_at else "",
        )
        for a in rows
    ]
