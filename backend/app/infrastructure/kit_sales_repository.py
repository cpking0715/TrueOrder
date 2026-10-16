"""出海包仓储（二）：开发信草稿快照、跟进到期、询盘与 PI 数据。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.kit_repository import company_display_name
from app.infrastructure.orm import CompanyORM, ContactORM, ProductORM, SuppressionORM
from app.infrastructure.orm_kit import KitDraftORM, KitInquiryORM, KitProductProfileORM


@dataclass(frozen=True)
class DraftParts:
    """生成草稿所需的素材（纯值，接口层不接触 ORM）。profile_* 为 None 表示未建档案。"""

    product_name: str
    has_profile: bool
    specs: str
    moq: int
    lead_time_days: int
    selling_points: tuple[str, ...]
    company_name: str
    country: str
    contact_name: str
    contact_email: str | None
    do_not_contact: bool


@dataclass(frozen=True)
class DraftRow:
    id: int
    product_id: int
    company_id: int
    company_name: str
    contact_id: int | None
    channel: str
    subject: str
    body: str
    source: str
    follow_up_on: list[date]


def _draft_row(d: KitDraftORM, company_name: str) -> DraftRow:
    return DraftRow(
        id=d.id, product_id=d.product_id, company_id=d.company_id, company_name=company_name,
        contact_id=d.contact_id, channel=d.channel, subject=d.subject, body=d.body,
        source=d.source, follow_up_on=list(d.follow_up_on or []),
    )


@dataclass(frozen=True)
class InquiryRow:
    id: int
    company_id: int
    company_name: str
    product_id: int
    product_name: str
    status: str
    quantity: int
    unit_price: Decimal
    currency: str
    note: str


class SqlKitSalesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------- 草稿 ----------

    def draft_parts(
        self, product_id: int, company_id: int, contact_id: int | None
    ) -> DraftParts | None:
        product = self._session.get(ProductORM, product_id)
        company = self._session.get(CompanyORM, company_id)
        if product is None or company is None:
            return None
        contact = None
        if contact_id is not None:
            contact = self._session.get(ContactORM, contact_id)
            if contact is None or contact.company_id != company_id:
                return None
        prof = self._session.get(KitProductProfileORM, product_id)
        return DraftParts(
            product_name=product.name,
            has_profile=prof is not None,
            specs=prof.specs if prof else "",
            moq=prof.moq if prof else 0,
            lead_time_days=prof.lead_time_days if prof else 0,
            selling_points=tuple(prof.selling_points or []) if prof else (),
            company_name=company_display_name(company),
            country=company.country,
            contact_name=(contact.name or "") if contact else "",
            contact_email=contact.email if contact else None,
            do_not_contact=bool(contact and contact.do_not_contact),
        )

    def suppression_dicts(self) -> list[dict[str, Any]]:
        return [
            {"email": s.email, "domain": s.domain}
            for s in self._session.scalars(select(SuppressionORM))
        ]

    def save_draft(
        self, *, product_id: int, company_id: int, contact_id: int | None, channel: str,
        subject: str, body: str, source: str, follow_up_on: list[date],
    ) -> DraftRow:
        row = KitDraftORM(
            product_id=product_id, company_id=company_id, contact_id=contact_id,
            channel=channel, subject=subject, body=body, source=source,
            follow_up_on=follow_up_on,
        )
        self._session.add(row)
        self._session.commit()
        return self.get_draft(row.id)  # type: ignore[return-value]

    def list_drafts(self) -> list[DraftRow]:
        stmt = (
            select(KitDraftORM, CompanyORM)
            .join(CompanyORM, CompanyORM.id == KitDraftORM.company_id)
            .order_by(KitDraftORM.id.desc())
        )
        return [_draft_row(d, company_display_name(c)) for d, c in self._session.execute(stmt)]

    def get_draft(self, draft_id: int) -> DraftRow | None:
        d = self._session.get(KitDraftORM, draft_id)
        if d is None:
            return None
        company = self._session.get(CompanyORM, d.company_id)
        return _draft_row(d, company_display_name(company) if company else "")

    # ---------- 询盘 ----------

    def create_inquiry(
        self, company_id: int, product_id: int, quantity: int, unit_price: Decimal,
        currency: str, note: str,
    ) -> int | None:
        if self._session.get(CompanyORM, company_id) is None:
            return None
        if self._session.get(ProductORM, product_id) is None:
            return None
        row = KitInquiryORM(
            company_id=company_id, product_id=product_id, status="new", quantity=quantity,
            unit_price=unit_price, currency=currency.upper(), note=note.strip(),
        )
        self._session.add(row)
        self._session.commit()
        return row.id

    def _rows(self, inquiry_id: int | None = None) -> list[InquiryRow]:
        stmt = (
            select(KitInquiryORM, CompanyORM, ProductORM)
            .join(CompanyORM, CompanyORM.id == KitInquiryORM.company_id)
            .join(ProductORM, ProductORM.id == KitInquiryORM.product_id)
            .order_by(KitInquiryORM.id.desc())
        )
        if inquiry_id is not None:
            stmt = stmt.where(KitInquiryORM.id == inquiry_id)
        return [
            InquiryRow(
                id=i.id, company_id=c.id, company_name=company_display_name(c),
                product_id=p.id, product_name=p.name, status=i.status, quantity=i.quantity,
                unit_price=i.unit_price, currency=i.currency, note=i.note,
            )
            for i, c, p in self._session.execute(stmt)
        ]

    def list_inquiries(self) -> list[InquiryRow]:
        return self._rows()

    def get_inquiry(self, inquiry_id: int) -> InquiryRow | None:
        rows = self._rows(inquiry_id)
        return rows[0] if rows else None

    def set_status(self, inquiry_id: int, status: str) -> None:
        row = self._session.get(KitInquiryORM, inquiry_id)
        if row is not None:
            row.status = status
            self._session.commit()

    def company_country(self, company_id: int) -> str:
        c = self._session.get(CompanyORM, company_id)
        return c.country if c else ""
