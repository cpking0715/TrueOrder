"""出海包仓储（一）：任务进度、产品档案、买家线索导入/标签。复用 products/companies/contacts。"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities import ImportSummary
from app.domain.kit import ProductProfileInput, clean_buyer_rows
from app.infrastructure.contact_repository import SqlContactRepository
from app.infrastructure.importers import CsvImporter
from app.infrastructure.orm import CompanyORM, ContactORM, ProductORM
from app.infrastructure.orm_kit import (
    KitBuyerTagORM,
    KitProductProfileORM,
    KitTaskProgressORM,
)


@dataclass(frozen=True)
class ProfileRow:
    product_id: int
    code: str
    name: str
    profile: KitProductProfileORM | None


@dataclass
class BuyerImportResult:
    rows_valid: int = 0
    companies_created: int = 0
    buyers_tagged: int = 0
    already_in_library: int = 0
    contacts_added: int = 0
    duplicates_in_file: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BuyerRow:
    company_id: int
    name: str
    country: str
    channel: str
    stage: str
    contact_id: int | None
    contact_name: str
    email: str | None


def company_display_name(c: CompanyORM) -> str:
    return (c.name_variants or [c.normalized_name])[0]


class SqlKitRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------- 任务进度 ----------

    def progress(self) -> dict[str, bool]:
        rows = self._session.scalars(select(KitTaskProgressORM))
        return {r.task_key: r.done for r in rows}

    def set_done(self, task_key: str, done: bool) -> None:
        row = self._session.get(KitTaskProgressORM, task_key)
        if row is None:
            self._session.add(KitTaskProgressORM(task_key=task_key, done=done))
        else:
            row.done = done
        self._session.commit()

    # ---------- 产品档案 ----------

    def list_profiles(self) -> list[ProfileRow]:
        stmt = (
            select(ProductORM, KitProductProfileORM)
            .outerjoin(KitProductProfileORM, KitProductProfileORM.product_id == ProductORM.id)
            .order_by(ProductORM.id)
        )
        return [ProfileRow(p.id, p.code, p.name, prof) for p, prof in self._session.execute(stmt)]

    def product_exists(self, product_id: int) -> bool:
        return self._session.get(ProductORM, product_id) is not None

    def featured_count(self) -> int:
        stmt = select(func.count()).select_from(KitProductProfileORM).where(
            KitProductProfileORM.featured.is_(True)
        )
        return int(self._session.scalar(stmt) or 0)

    def get_profile(self, product_id: int) -> KitProductProfileORM | None:
        return self._session.get(KitProductProfileORM, product_id)

    def upsert_profile(self, product_id: int, p: ProductProfileInput) -> None:
        row = self.get_profile(product_id)
        if row is None:
            row = KitProductProfileORM(product_id=product_id)
            self._session.add(row)
        row.image_url = p.image_url.strip()
        row.specs = p.specs.strip()
        row.moq = p.moq
        row.lead_time_days = p.lead_time_days
        row.selling_points = [s.strip() for s in p.selling_points if s.strip()]
        row.featured = p.featured
        self._session.commit()

    # ---------- 买家线索 ----------

    def import_buyers(self, csv_text: str, source_ref: str) -> BuyerImportResult:
        """清洗 → 企业按「规范化名+国家」复用/新建 → 打标签 → 有邮箱则写联系人（来源 csv）。"""
        cleaned = clean_buyer_rows(csv.DictReader(io.StringIO(csv_text)))
        result = BuyerImportResult(
            rows_valid=len(cleaned.valid),
            duplicates_in_file=cleaned.duplicates,
            errors=list(cleaned.errors),
        )
        summary = ImportSummary()
        importer = CsvImporter(self._session)
        contacts = SqlContactRepository(self._session)
        for b in cleaned.valid:
            company_id = importer._upsert_company(b.company_name, "", b.country, summary)
            if company_id is None:  # 清洗已保证企业名非空，这里只做防御
                continue
            if self._session.get(KitBuyerTagORM, company_id) is None:
                self._session.add(
                    KitBuyerTagORM(
                        company_id=company_id,
                        channel=b.channel,
                        stage=b.stage,
                        source_ref=source_ref,
                    )
                )
                result.buyers_tagged += 1
            else:
                result.already_in_library += 1
            self._session.commit()
            if (b.email or b.phone) and not self._phone_only_dup(company_id, b.email, b.phone):
                added = contacts.add(
                    company_id, name=b.contact_name or None, title="", email=b.email,
                    phone=b.phone or None, source="csv", source_ref=source_ref,
                )
                result.contacts_added += 1 if added.error is None else 0
        result.companies_created = summary.companies_created
        return result

    def _phone_only_dup(self, company_id: int, email: str | None, phone: str) -> bool:
        """无邮箱的联系人按「公司+电话」查重（既有仓储只按邮箱查重），保证二次导入 0 新增。"""
        if email:
            return False
        stmt = select(ContactORM.id).where(
            ContactORM.company_id == company_id, ContactORM.phone == phone
        )
        return self._session.scalar(stmt) is not None

    def list_buyers(
        self, country: str = "", channel: str = "", stage: str = ""
    ) -> list[BuyerRow]:
        stmt = (
            select(KitBuyerTagORM, CompanyORM)
            .join(CompanyORM, CompanyORM.id == KitBuyerTagORM.company_id)
            .order_by(CompanyORM.id)
        )
        if country:
            stmt = stmt.where(CompanyORM.country == country.upper())
        if channel:
            stmt = stmt.where(KitBuyerTagORM.channel == channel)
        if stage:
            stmt = stmt.where(KitBuyerTagORM.stage == stage)
        pairs = list(self._session.execute(stmt))
        first_contact = self._first_contacts([c.id for _, c in pairs])
        out = []
        for tag, c in pairs:
            ct = first_contact.get(c.id)
            out.append(
                BuyerRow(
                    company_id=c.id, name=company_display_name(c), country=c.country,
                    channel=tag.channel, stage=tag.stage,
                    contact_id=ct.id if ct else None,
                    contact_name=(ct.name or "") if ct else "",
                    email=ct.email if ct else None,
                )
            )
        return out

    def _first_contacts(self, company_ids: list[int]) -> dict[int, ContactORM]:
        if not company_ids:
            return {}
        stmt = (
            select(ContactORM)
            .where(ContactORM.company_id.in_(company_ids))
            .order_by(ContactORM.company_id, ContactORM.id)
        )
        found: dict[int, ContactORM] = {}
        for ct in self._session.scalars(stmt):
            found.setdefault(ct.company_id, ct)
        return found

    def update_buyer_tags(self, company_id: int, channel: str | None, stage: str | None) -> bool:
        tag = self._session.get(KitBuyerTagORM, company_id)
        if tag is None:
            return False
        if channel is not None:
            tag.channel = channel
        if stage is not None:
            tag.stage = stage
        self._session.commit()
        return True
