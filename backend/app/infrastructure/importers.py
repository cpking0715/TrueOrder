"""CSV 导入器：产品目录与提单（含企业归并、去重、导入后重打分）。"""

from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import BillLine, ImportSummary
from app.domain.normalize import (
    guess_city,
    is_valid_hs,
    name_conflict,
    normalize_company_name,
    normalize_country,
)
from app.domain.parse import bill_dedup_hash, parse_bill_row, parse_product_rows
from app.domain.services import RescoreService, RescoreSummary
from app.infrastructure.orm import CompanyORM, RawBillORM
from app.infrastructure.queries import SqlBuyerQueries
from app.infrastructure.repositories import SqlBuyerPoolReader, SqlProductRepository, SqlScoreWriter


class CsvImporter:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------- 产品目录 ----------

    def import_products(self, csv_text: str, source: str = "products.csv") -> ImportSummary:
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        products, errors = parse_product_rows(rows, source)
        summary = ImportSummary(invalid_rows=errors)
        repo = SqlProductRepository(self._session)
        for product in products:
            repo.upsert_product(product)
            summary.products_upserted += 1
            summary.hs_assignments_written += len(product.hs_assignments)
        self._session.commit()
        return summary

    # ---------- 提单 ----------

    def import_bills(
        self,
        csv_text: str,
        source_ref: str = "bills.csv",
        as_of: date | None = None,
        rescore: bool = True,
    ) -> tuple[ImportSummary, list[RescoreSummary]]:
        summary = ImportSummary()
        rescores: list[RescoreSummary] = []
        lines: list[tuple[BillLine, int]] = []
        for row_no, row in enumerate(csv.DictReader(io.StringIO(csv_text)), start=2):
            line, err = parse_bill_row(row, source_ref, row_no)
            if err or line is None:
                if err:
                    summary.invalid_rows.append(err)
                continue
            lines.append((line, row_no))

        hashes = [bill_dedup_hash(line) for line, _ in lines]
        existing = set(
            self._session.scalars(
                select(RawBillORM.bill_hash).where(RawBillORM.bill_hash.in_(hashes))
            )
        )

        for (line, row_no), bill_hash in zip(lines, hashes, strict=True):
            if bill_hash in existing:
                summary.duplicate_bills += 1
                continue
            consignee_id = self._upsert_company(
                line.consignee_name,
                line.consignee_address,
                raw_country=line.consignee_country or "US",
                summary=summary,
            )
            shipper_id = (
                self._upsert_company(
                    line.shipper_name,
                    line.shipper_address,
                    raw_country=line.shipper_country or line.origin_country or "US",
                    summary=summary,
                )
                if line.shipper_name
                else None
            )

            suspect = not is_valid_hs(line.hs_code)
            if suspect and line.hs_code:
                summary.suspect_hs_bills += 1
            self._session.add(
                RawBillORM(
                    source_ref=source_ref,
                    row_no=row_no,
                    bill_hash=bill_hash,
                    arrival_date=line.arrival_date,
                    consignee_company_id=consignee_id,
                    consignee_raw=line.consignee_name,
                    consignee_address=line.consignee_address,
                    shipper_company_id=shipper_id,
                    shipper_raw=line.shipper_name,
                    shipper_address=line.shipper_address,
                    hs_code=line.hs_code,
                    hs_suspect=suspect,
                    product_description=line.product_description,
                    origin_country=normalize_country(line.origin_country),
                    port=line.port,
                    bill_number=line.bill_number,
                    quantity=line.quantity,
                )
            )
            summary.inserted_bills += 1

        if rescore:
            rescores = self.rescore(as_of or date.today())
        self._session.commit()
        return summary, rescores

    def _upsert_company(
        self,
        raw_name: str,
        address: str,
        raw_country: str,
        summary: ImportSummary,
    ) -> int | None:
        normalized = normalize_company_name(raw_name)
        if not normalized:
            return None
        country = normalize_country(raw_country) or "US"
        existing = self._session.scalar(
            select(CompanyORM).where(
                CompanyORM.normalized_name == normalized, CompanyORM.country == country
            )
        )
        if existing is None:
            company = CompanyORM(
                normalized_name=normalized,
                country=country,
                name_variants=[raw_name] if raw_name else [],
                variant_addresses=[address] if address else [],
                address_guess=address,
                city_guess=guess_city(address),
            )
            _refresh_search_text(company)
            self._session.add(company)
            self._session.flush()
            summary.companies_created += 1
            return company.id

        changed = False
        if raw_name and raw_name not in (existing.name_variants or []):
            existing.name_variants = [*existing.name_variants, raw_name]
            existing.variant_addresses = [*(existing.variant_addresses or []), address]
            changed = True
        if address and not existing.address_guess:
            existing.address_guess = address
            existing.city_guess = guess_city(address)
            changed = True
        if changed:
            pairs = list(
                zip(existing.name_variants or [], existing.variant_addresses or [], strict=False)
            )
            existing.same_name_conflict = name_conflict(pairs)
            _refresh_search_text(existing)
            summary.companies_updated += 1
        return existing.id

    def rescore(self, as_of: date) -> list[RescoreSummary]:
        service = RescoreService(
            products=SqlProductRepository(self._session),
            pool=SqlBuyerPoolReader(self._session),
            scores=SqlScoreWriter(self._session),
        )
        result = service.rescore_all(as_of)
        self._session.commit()
        return result


def build_rescore_service(session: Session) -> RescoreService:
    return RescoreService(
        products=SqlProductRepository(session),
        pool=SqlBuyerPoolReader(session),
        scores=SqlScoreWriter(session),
    )


def _refresh_search_text(company: CompanyORM) -> None:
    parts = [*(company.name_variants or []), company.address_guess or "", company.city_guess or ""]
    company.search_text = " ".join(p for p in parts if p)


__all__ = ["CsvImporter", "SqlBuyerQueries", "build_rescore_service"]
