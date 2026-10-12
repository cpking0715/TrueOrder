"""商机仓储（WP2）：加入跟进、阶段变更（自动写 stage_change 活动）、列表/到期/时间线。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.pipeline import validate_transition
from app.infrastructure.orm import ActivityORM, CompanyORM, OpportunityORM


@dataclass(frozen=True)
class OpportunityRow:
    opportunity_id: int
    product_id: int
    company_id: int
    company_name: str
    stage: str
    intent: str
    next_follow_up_on: date | None
    owner_note: str
    closed_reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ActivityRow:
    activity_id: int
    opportunity_id: int
    contact_id: int | None
    kind: str
    summary: str
    body: str
    intent_after: str | None
    occurred_at: datetime


def _to_row(o: OpportunityORM, company_name: str) -> OpportunityRow:
    return OpportunityRow(
        opportunity_id=o.id,
        product_id=o.product_id,
        company_id=o.company_id,
        company_name=company_name,
        stage=o.stage,
        intent=o.intent,
        next_follow_up_on=o.next_follow_up_on,
        owner_note=o.owner_note or "",
        closed_reason=o.closed_reason,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


class SqlOpportunityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self, product_id: int, company_id: int, owner_note: str = ""
    ) -> tuple[OpportunityRow, bool]:
        """从买家列表加入跟进：已存在返回（既有, False）；新建写一条 note 活动。"""
        existing = self._session.scalar(
            select(OpportunityORM).where(
                OpportunityORM.product_id == product_id,
                OpportunityORM.company_id == company_id,
            )
        )
        if existing is not None:
            name = self._company_name(company_id)
            self._session.rollback()
            return _to_row(existing, name), False
        opp = OpportunityORM(
            product_id=product_id, company_id=company_id, owner_note=owner_note
        )
        self._session.add(opp)
        self._session.flush()
        if owner_note:
            self._session.add(
                ActivityORM(opportunity_id=opp.id, kind="note", summary=owner_note)
            )
        self._session.commit()
        return _to_row(opp, self._company_name(company_id)), True

    def get(self, opportunity_id: int) -> OpportunityRow | None:
        o = self._session.get(OpportunityORM, opportunity_id)
        return _to_row(o, self._company_name(o.company_id)) if o else None

    def find(self, product_id: int, company_id: int) -> OpportunityRow | None:
        o = self._session.scalar(
            select(OpportunityORM).where(
                OpportunityORM.product_id == product_id,
                OpportunityORM.company_id == company_id,
            )
        )
        return _to_row(o, self._company_name(company_id)) if o else None

    def list_opportunities(
        self,
        product_id: int | None = None,
        stage: str | None = None,
        due_on: date | None = None,
    ) -> list[OpportunityRow]:
        stmt = (
            select(OpportunityORM, CompanyORM.normalized_name)
            .join(CompanyORM, OpportunityORM.company_id == CompanyORM.id)
            .order_by(OpportunityORM.id)
        )
        if product_id:
            stmt = stmt.where(OpportunityORM.product_id == product_id)
        if stage:
            stmt = stmt.where(OpportunityORM.stage == stage)
        rows: list[OpportunityRow] = []
        for o, name in self._session.execute(stmt):
            if due_on is not None:
                if o.next_follow_up_on is None or o.next_follow_up_on > due_on:
                    continue
                if o.stage in ("won_intent", "lost"):
                    continue
            rows.append(_to_row(o, name))
        return rows

    def update(
        self,
        opportunity_id: int,
        *,
        stage: str | None = None,
        closed_reason: str | None = None,
        intent: str | None = None,
        next_follow_up_on: date | None = None,
        owner_note: str | None = None,
    ) -> OpportunityRow | str:
        """返回更新后行；'invalid_transition'/错误文本 表示业务失败；None 语义见调用方。"""
        o = self._session.get(OpportunityORM, opportunity_id)
        if o is None:
            return "not_found"
        if stage is not None and stage != o.stage:
            error = validate_transition(o.stage, stage, closed_reason or o.closed_reason or "")
            if error:
                return error
            self._session.add(
                ActivityORM(
                    opportunity_id=o.id,
                    kind="stage_change",
                    summary=f"{o.stage} → {stage}",
                )
            )
            o.stage = stage
            if stage == "lost":
                o.closed_reason = closed_reason
            if stage == "lead" and o.closed_reason:  # lost→lead 重开清原因
                o.closed_reason = None
        if intent is not None:
            o.intent = intent
        if next_follow_up_on is not None:
            o.next_follow_up_on = next_follow_up_on
        if owner_note is not None:
            o.owner_note = owner_note
        self._session.commit()
        return _to_row(o, self._company_name(o.company_id))

    def add_activity(
        self,
        opportunity_id: int,
        *,
        kind: str,
        summary: str,
        body: str = "",
        contact_id: int | None = None,
        intent_after: str | None = None,
    ) -> ActivityRow | str:
        o = self._session.get(OpportunityORM, opportunity_id)
        if o is None:
            return "not_found"
        if kind not in ("email_out", "email_in", "call", "whatsapp", "note"):
            return "invalid_kind"
        a = ActivityORM(
            opportunity_id=opportunity_id,
            contact_id=contact_id,
            kind=kind,
            summary=summary,
            body=body,
            intent_after=intent_after,
        )
        self._session.add(a)
        if intent_after:
            o.intent = intent_after
        self._session.commit()
        return ActivityRow(
            activity_id=a.id,
            opportunity_id=a.opportunity_id,
            contact_id=a.contact_id,
            kind=a.kind,
            summary=a.summary or "",
            body=a.body or "",
            intent_after=a.intent_after,
            occurred_at=a.occurred_at,
        )

    def timeline(self, opportunity_id: int) -> list[ActivityRow] | None:
        if self._session.get(OpportunityORM, opportunity_id) is None:
            return None
        rows = self._session.scalars(
            select(ActivityORM)
            .where(ActivityORM.opportunity_id == opportunity_id)
            .order_by(ActivityORM.id.desc())
        )
        return [
            ActivityRow(
                activity_id=a.id,
                opportunity_id=a.opportunity_id,
                contact_id=a.contact_id,
                kind=a.kind,
                summary=a.summary or "",
                body=a.body or "",
                intent_after=a.intent_after,
                occurred_at=a.occurred_at,
            )
            for a in rows
        ]

    def _company_name(self, company_id: int) -> str:
        company = self._session.get(CompanyORM, company_id)
        if company is None:
            return ""
        return (company.name_variants or [company.normalized_name])[0]


def today_utc() -> date:
    return datetime.now(UTC).date()
