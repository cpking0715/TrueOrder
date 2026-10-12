"""联系人仓储：CRUD、CSV 导入、官网字段更新（WP1）。"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.contacts import is_generic_email, is_valid_email, normalize_email
from app.infrastructure.orm import CompanyORM, ContactORM


@dataclass
class ContactRow:
    contact_id: int
    company_id: int
    name: str | None
    title: str
    email: str | None
    phone: str | None
    is_generic: bool
    source: str
    source_ref: str
    acquired_at: datetime
    verify_status: str
    do_not_contact: bool


def _to_row(c: ContactORM) -> ContactRow:
    return ContactRow(
        contact_id=c.id,
        company_id=c.company_id,
        name=c.name,
        title=c.title or "",
        email=c.email,
        phone=c.phone,
        is_generic=bool(c.is_generic),
        source=c.source,
        source_ref=c.source_ref or "",
        acquired_at=c.acquired_at,
        verify_status=c.verify_status,
        do_not_contact=bool(c.do_not_contact),
    )


@dataclass
class AddContactResult:
    contact: ContactRow | None
    error: str | None  # 'duplicate' | 'invalid_email' | None


@dataclass
class ContactsImportSummary:
    added: int = 0
    duplicates: int = 0
    company_not_found: list[str] = None  # type: ignore[assignment]
    invalid_rows: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.company_not_found = self.company_not_found or []
        self.invalid_rows = self.invalid_rows or []


@dataclass
class ExportContactRow:
    """导出用的联系人行（含官网字段；官网置信度列待 WP4）。"""

    name: str | None
    title: str
    email: str | None
    phone: str | None
    is_generic: bool
    verify_status: str
    source: str
    source_ref: str
    acquired_at: datetime
    website: str | None
    website_confidence: str = ""


class SqlContactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------- 查询 ----------

    def list_by_company(self, company_id: int) -> list[ContactRow]:
        rows = self._session.scalars(
            select(ContactORM)
            .where(ContactORM.company_id == company_id)
            .order_by(ContactORM.id)
        )
        return [_to_row(c) for c in rows]

    def get(self, contact_id: int) -> ContactRow | None:
        c = self._session.get(ContactORM, contact_id)
        return _to_row(c) if c else None

    def company_exists(self, company_id: int) -> bool:
        return self._session.get(CompanyORM, company_id) is not None

    # ---------- 写入 ----------

    def add(
        self,
        company_id: int,
        *,
        name: str | None,
        title: str,
        email: str | None,
        phone: str | None,
        source: str,
        source_ref: str = "",
    ) -> AddContactResult:
        normalized = normalize_email(email)
        if normalized is not None and not is_valid_email(normalized):
            return AddContactResult(None, "invalid_email")
        if self._duplicate_exists(company_id, normalized):
            return AddContactResult(None, "duplicate")
        contact = ContactORM(
            company_id=company_id,
            name=(name or "").strip() or None,
            title=(title or "").strip(),
            email=normalized,
            phone=(phone or "").strip() or None,
            is_generic=is_generic_email(normalized) if normalized else False,
            source=source,
            source_ref=source_ref,
        )
        self._session.add(contact)
        try:
            self._session.flush()
        except IntegrityError:
            # 并发窗口兜底：唯一索引拦下，回滚保持会话可用（预查重已覆盖常规路径）
            self._session.rollback()
            return AddContactResult(None, "duplicate")
        self._session.commit()  # 响应前落库：客户端拿到 2xx 时数据必须已持久化
        return AddContactResult(_to_row(contact), None)

    def _duplicate_exists(
        self, company_id: int, normalized_email: str | None, exclude_contact_id: int | None = None
    ) -> bool:
        """公司内同邮箱查重（同事务内已 flush 的行也可见，导入循环内重复即时命中）。"""
        if normalized_email is None:
            return False
        stmt = select(ContactORM.id).where(
            ContactORM.company_id == company_id,
            func.lower(ContactORM.email) == normalized_email,
        )
        if exclude_contact_id is not None:
            stmt = stmt.where(ContactORM.id != exclude_contact_id)
        return self._session.scalar(stmt) is not None

    def update(
        self, contact_id: int, *, name: str | None, title: str | None, email: str | None,
        phone: str | None, do_not_contact: bool | None,
    ) -> ContactRow | str | None:
        """返回更新后的行；'duplicate'/'invalid_email' 表示业务失败；None 表示不存在。"""
        contact = self._session.get(ContactORM, contact_id)
        if contact is None:
            return None
        # 先校验再改字段：invalid_email / duplicate 提前返回，不留脏改动
        normalized_new = None
        if email is not None:
            normalized_new = normalize_email(email)
            if normalized_new is not None and not is_valid_email(normalized_new):
                return "invalid_email"
            if self._duplicate_exists(
                contact.company_id, normalized_new, exclude_contact_id=contact_id
            ):
                return "duplicate"
        if name is not None:
            contact.name = name.strip() or None
        if title is not None:
            contact.title = title.strip()
        if phone is not None:
            contact.phone = phone.strip() or None
        if do_not_contact is not None:
            contact.do_not_contact = do_not_contact
        if email is not None:
            contact.email = normalized_new
            contact.is_generic = is_generic_email(normalized_new) if normalized_new else False
        try:
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            return "duplicate"
        self._session.commit()
        return _to_row(contact)

    def delete(self, contact_id: int) -> bool:
        contact = self._session.get(ContactORM, contact_id)
        if contact is None:
            return False
        self._session.delete(contact)
        self._session.flush()
        self._session.commit()
        return True

    def update_website(
        self, company_id: int, website: str | None, confirmed: bool | None
    ) -> tuple[str | None, bool] | None:
        """返回 (website, website_confirmed)；公司不存在返回 None。"""
        company = self._session.get(CompanyORM, company_id)
        if company is None:
            return None
        if website is not None:
            company.website = website.strip() or None
        if confirmed is not None:
            company.website_confirmed = confirmed
        self._session.flush()
        self._session.commit()
        return company.website, bool(company.website_confirmed)

    # ---------- CSV 导入 ----------

    def import_csv(self, csv_text: str, source_ref: str = "contacts.csv") -> ContactsImportSummary:
        summary = ContactsImportSummary()
        for row_no, row in enumerate(csv.DictReader(io.StringIO(csv_text)), start=2):
            company_id, resolve_error = self._resolve_company(row)
            if resolve_error == "missing_country":
                summary.invalid_rows.append(f"第 {row_no} 行：按企业名定位必须提供国家")
                continue
            if resolve_error == "missing_target":
                summary.invalid_rows.append(f"第 {row_no} 行：缺少 company_id 或企业名")
                continue
            if resolve_error == "not_found":
                summary.company_not_found.append(f"第 {row_no} 行：企业未找到")
                continue
            result = self.add(
                company_id,
                name=row.get("name"),
                title=row.get("title") or "",
                email=row.get("email"),
                phone=row.get("phone"),
                source="csv",
                source_ref=source_ref,
            )
            if result.error == "duplicate":
                summary.duplicates += 1
            elif result.error == "invalid_email":
                summary.invalid_rows.append(
                    f"第 {row_no} 行：邮箱格式非法 {row.get('email')!r}"
                )
            else:
                summary.added += 1
        # add 内行级 commit：导入语义为逐行持久化（非原子），已知行为见 HANDOFF
        return summary

    def _resolve_company(self, row: dict) -> tuple[int | None, str | None]:
        """返回 (company_id, error)；error: 'missing_country' | 'not_found' | 'missing_target'。"""
        raw_id = (row.get("company_id") or "").strip()
        if raw_id.isdigit():
            if self.company_exists(int(raw_id)):
                return int(raw_id), None
            return None, "not_found"
        from app.domain.normalize import normalize_company_name, normalize_country

        name = normalize_company_name(row.get("company_name") or "")
        if not name:
            return None, "missing_target"
        raw_country = (row.get("country") or "").strip()
        if not raw_country:
            # 静默默认 US 会把联系人错挂到同名美国公司：名称定位必须带国家
            return None, "missing_country"
        country = normalize_country(raw_country) or "US"
        company_id = self._session.scalar(
            select(CompanyORM.id).where(
                CompanyORM.normalized_name == name, CompanyORM.country == country
            )
        )
        return company_id, None if company_id else "not_found"

    # ---------- 导出 ----------

    def export_rows(
        self, company_ids: list[int], *, include_invalid: bool
    ) -> list[tuple[int, ExportContactRow]]:
        """按公司批量取导出用联系人（保序去重 company_ids）。

        默认排除 do_not_contact 与 verify_status in (invalid, bounced)。
        返回 (company_id, ExportContactRow)，含官网字段。
        """
        unique_ids = list(dict.fromkeys(company_ids))
        if not unique_ids:
            return []
        stmt = (
            select(ContactORM, CompanyORM.website, CompanyORM.website_confidence)
            .join(CompanyORM, ContactORM.company_id == CompanyORM.id)
            .where(ContactORM.company_id.in_(unique_ids))
            .order_by(ContactORM.company_id, ContactORM.id)
        )
        # do_not_contact 是联系意愿，任何导出都不放开；include_invalid 只放开验证状态
        stmt = stmt.where(ContactORM.do_not_contact.is_(False))
        if not include_invalid:
            stmt = stmt.where(ContactORM.verify_status.notin_(["invalid", "bounced"]))
        result: list[tuple[int, ExportContactRow]] = []
        for contact, website, website_confidence in self._session.execute(stmt):
            result.append(
                (
                    contact.company_id,
                    ExportContactRow(
                        name=contact.name,
                        title=contact.title or "",
                        email=contact.email,
                        phone=contact.phone,
                        is_generic=bool(contact.is_generic),
                        verify_status=contact.verify_status,
                        source=contact.source,
                        source_ref=contact.source_ref or "",
                        acquired_at=contact.acquired_at,
                        website=website,
                        website_confidence=website_confidence or "",
                    ),
                )
            )
        return result

    def companies_with_contacts(self, company_ids: list[int]) -> set[int]:
        """已有任何联系人的公司（批量补全时跳过）。"""
        if not company_ids:
            return set()
        rows = self._session.scalars(
            select(ContactORM.company_id)
            .where(ContactORM.company_id.in_(company_ids))
            .distinct()
        )
        return set(rows)
