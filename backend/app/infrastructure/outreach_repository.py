"""开发信持久化（模板、消息、抑制名单）：路由层只拿值对象，不碰 ORM。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.jobs import SqlJobQueue
from app.infrastructure.orm import (
    CompanyORM,
    ContactORM,
    EmailMessageORM,
    EmailTemplateORM,
    OpportunityORM,
    ProductORM,
    SuppressionORM,
)


@dataclass(frozen=True)
class TemplateRecord:
    id: int
    name: str
    subject: str
    body: str
    language: str


@dataclass(frozen=True)
class ContactRecord:
    id: int
    name: str
    email: str
    do_not_contact: bool
    verify_status: str | None
    source: str | None
    source_ref: str | None


@dataclass(frozen=True)
class MessageRecord:
    id: int
    opportunity_id: int
    contact_id: int | None
    subject: str
    status: str
    error: str | None
    sent_at: datetime | None


@dataclass(frozen=True)
class SuppressionRecord:
    id: int
    email: str | None
    domain: str | None
    reason: str


class DuplicateTemplateError(Exception):
    pass


def _tpl(t: EmailTemplateORM) -> TemplateRecord:
    return TemplateRecord(t.id, t.name, t.subject, t.body, t.language)


def _sup(s: SuppressionORM) -> SuppressionRecord:
    return SuppressionRecord(s.id, s.email, s.domain, s.reason)


class SqlOutreachRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- 模板 ----
    def list_templates(self) -> list[TemplateRecord]:
        stmt = select(EmailTemplateORM).order_by(EmailTemplateORM.id)
        return [_tpl(t) for t in self._session.scalars(stmt)]

    def get_template(self, template_id: int) -> TemplateRecord | None:
        t = self._session.get(EmailTemplateORM, template_id)
        return _tpl(t) if t else None

    def create_template(self, name: str, subject: str, body: str, language: str) -> TemplateRecord:
        exists = self._session.scalar(
            select(EmailTemplateORM.id).where(EmailTemplateORM.name == name)
        )
        if exists:
            raise DuplicateTemplateError(name)
        t = EmailTemplateORM(name=name, subject=subject, body=body, language=language)
        self._session.add(t)
        self._session.commit()
        return _tpl(t)

    def delete_template(self, template_id: int) -> bool:
        t = self._session.get(EmailTemplateORM, template_id)
        if t is None:
            return False
        self._session.delete(t)
        self._session.commit()
        return True

    # ---- 渲染上下文 ----
    def get_contact(self, contact_id: int) -> ContactRecord | None:
        c = self._session.get(ContactORM, contact_id)
        if c is None:
            return None
        return ContactRecord(
            id=c.id,
            name=c.name or "",
            email=c.email or "",
            do_not_contact=bool(c.do_not_contact),
            verify_status=c.verify_status,
            source=c.source,
            source_ref=c.source_ref,
        )

    def opportunity_exists(self, opportunity_id: int) -> bool:
        return self._session.get(OpportunityORM, opportunity_id) is not None

    def company_and_product_names(self, opportunity_id: int) -> tuple[str, str]:
        opp = self._session.get(OpportunityORM, opportunity_id)
        if opp is None:
            return "", ""
        company = self._session.get(CompanyORM, opp.company_id)
        product = self._session.get(ProductORM, opp.product_id)
        return (company.normalized_name if company else "", product.name if product else "")

    def suppression_dicts(self) -> list[dict[str, Any]]:
        return [
            {"email": s.email, "domain": s.domain}
            for s in self._session.scalars(select(SuppressionORM))
        ]

    # ---- 消息 ----
    def queue_message(
        self, opportunity_id: int, contact_id: int, template_id: int, subject: str, body: str
    ) -> int:
        """建消息 + 入队 send_email，同一事务提交。"""
        msg = EmailMessageORM(
            opportunity_id=opportunity_id,
            contact_id=contact_id,
            template_id=template_id,
            subject=subject,
            body=body,
        )
        self._session.add(msg)
        self._session.flush()
        SqlJobQueue(self._session).enqueue("send_email", {"message_id": msg.id})
        self._session.commit()
        return msg.id

    def list_messages(self, status: str | None, limit: int) -> list[MessageRecord]:
        stmt = select(EmailMessageORM).order_by(EmailMessageORM.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(EmailMessageORM.status == status)
        return [
            MessageRecord(
                m.id, m.opportunity_id, m.contact_id, m.subject, m.status, m.error, m.sent_at
            )
            for m in self._session.scalars(stmt)
        ]

    # ---- 抑制名单 ----
    def list_suppressions(self) -> list[SuppressionRecord]:
        stmt = select(SuppressionORM).order_by(SuppressionORM.id)
        return [_sup(s) for s in self._session.scalars(stmt)]

    def add_suppression(
        self, email: str | None, domain: str | None, reason: str
    ) -> SuppressionRecord:
        s = SuppressionORM(email=email, domain=domain, reason=reason)
        self._session.add(s)
        self._session.commit()
        return _sup(s)

    def delete_suppression(self, suppression_id: int) -> bool:
        s = self._session.get(SuppressionORM, suppression_id)
        if s is None:
            return False
        self._session.delete(s)
        self._session.commit()
        return True
