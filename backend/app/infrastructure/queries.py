"""界面查询：买家列表（FTS + 筛选）、产品计数、公司抽屉详情。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.infrastructure.orm import (
    CompanyORM,
    CompanyScoreORM,
    ProductHsCodeORM,
    ProductORM,
    RawBillORM,
)


@dataclass
class BuyerQueryFilters:
    product_id: int
    audience: str  # importer / factory
    tier: str | None = None  # potential / precise / excluded；None = 全部
    q: str | None = None  # PostgreSQL 全文检索
    country: str | None = None
    min_shipments: int | None = None
    order: str = "shipments"  # shipments | last_arrival | name
    limit: int = 50
    offset: int = 0


@dataclass
class BuyerRow:
    company_id: int
    name: str
    normalized_name: str
    country: str
    city: str
    same_name_conflict: bool
    tier: str
    exclusion_code: str | None
    shipments: int
    last_arrival: date | None
    suppliers: list[str]
    reasons: list[dict]


@dataclass
class CompanyDetail:
    company: dict
    scores: list[dict] = field(default_factory=list)
    bills: list[dict] = field(default_factory=list)
    bills_truncated: bool = False


def _fts_condition(q: str) -> ColumnElement[bool] | None:
    query = (q or "").strip()
    if not query:
        return None
    ts_query = func.websearch_to_tsquery("simple", query)
    return CompanyORM.search_vector.op("@@")(ts_query)


class SqlBuyerQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def query_buyers(self, f: BuyerQueryFilters) -> tuple[list[BuyerRow], int]:
        stmt = (
            select(CompanyScoreORM, CompanyORM)
            .join(CompanyORM, CompanyScoreORM.company_id == CompanyORM.id)
            .where(
                CompanyScoreORM.product_id == f.product_id,
                CompanyScoreORM.audience == f.audience,
            )
        )
        if f.tier:
            stmt = stmt.where(CompanyScoreORM.tier == f.tier)
        if f.country:
            stmt = stmt.where(CompanyORM.country == f.country.upper())
        if f.min_shipments:
            stmt = stmt.where(CompanyScoreORM.shipments >= f.min_shipments)
        fts = _fts_condition(f.q or "")
        if fts is not None:
            stmt = stmt.where(fts)

        total = self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

        if f.order == "last_arrival":
            stmt = stmt.order_by(
                func.coalesce(CompanyScoreORM.last_arrival, date(1970, 1, 1)).desc()
            )
        elif f.order == "name":
            stmt = stmt.order_by(CompanyORM.normalized_name.asc())
        else:
            stmt = stmt.order_by(
                CompanyScoreORM.shipments.desc(), CompanyORM.normalized_name.asc()
            )

        rows = self._session.execute(stmt.limit(f.limit).offset(f.offset)).all()
        items = [
            BuyerRow(
                company_id=company.id,
                name=(company.name_variants or [company.normalized_name])[0],
                normalized_name=company.normalized_name,
                country=company.country,
                city=company.city_guess or "",
                same_name_conflict=bool(company.same_name_conflict),
                tier=score.tier,
                exclusion_code=score.exclusion_code,
                shipments=score.shipments,
                last_arrival=score.last_arrival,
                suppliers=list(score.suppliers or []),
                reasons=list(score.reasons or []),
            )
            for score, company in rows
        ]
        return items, int(total)

    def product_tier_counts(self) -> dict[int, dict[str, dict[str, int]]]:
        """按 (product_id, audience) 分层的 tier 计数；both 产品两类受众不混加。"""
        rows = self._session.execute(
            select(
                CompanyScoreORM.product_id,
                CompanyScoreORM.audience,
                CompanyScoreORM.tier,
                func.count(),
            ).group_by(CompanyScoreORM.product_id, CompanyScoreORM.audience, CompanyScoreORM.tier)
        ).all()
        counts: dict[int, dict[str, dict[str, int]]] = {}
        for product_id, audience, tier, n in rows:
            counts.setdefault(product_id, {}).setdefault(audience, {})[tier] = int(n)
        return counts

    @staticmethod
    def _summed_counts(by_audience: dict[str, dict[str, int]]) -> dict[str, int]:
        total: dict[str, int] = {}
        for tier_counts in by_audience.values():
            for tier, n in tier_counts.items():
                total[tier] = total.get(tier, 0) + n
        return total

    def list_products_with_counts(self) -> list[dict]:
        counts_by_audience = self.product_tier_counts()
        products = self._session.execute(
            select(
                ProductORM,
                ProductHsCodeORM.hs_code,
                ProductHsCodeORM.audience,
                ProductHsCodeORM.note,
            )
            .outerjoin(ProductHsCodeORM, ProductHsCodeORM.product_id == ProductORM.id)
            .order_by(ProductORM.id, ProductHsCodeORM.id)
        ).all()
        by_id: dict[int, dict] = {}
        for product, hs_code, audience, note in products:
            by_audience = counts_by_audience.get(product.id, {})
            entry = by_id.setdefault(
                product.id,
                {
                    "product_id": product.id,
                    "code": product.code,
                    "name": product.name,
                    "description": product.description,
                    "buyer_type": product.buyer_type,
                    "hs_codes": [],
                    "counts": self._summed_counts(by_audience),
                    "counts_by_audience": by_audience,
                },
            )
            if hs_code:
                entry["hs_codes"].append(
                    {"hs_code": hs_code, "audience": audience, "note": note or ""}
                )
        return list(by_id.values())

    def get_product_with_counts(self, product_id: int) -> dict | None:
        """单产品详情（含 tier 计数与税号列表），不拉全表。"""
        product = self._session.get(ProductORM, product_id)
        if product is None:
            return None
        hs_rows = self._session.scalars(
            select(ProductHsCodeORM)
            .where(ProductHsCodeORM.product_id == product_id)
            .order_by(ProductHsCodeORM.id)
        ).all()
        by_audience = self.product_tier_counts().get(product_id, {})
        return {
            "product_id": product.id,
            "code": product.code,
            "name": product.name,
            "description": product.description,
            "buyer_type": product.buyer_type,
            "hs_codes": [
                {"hs_code": r.hs_code, "audience": r.audience, "note": r.note or ""}
                for r in hs_rows
            ],
            "counts": self._summed_counts(by_audience),
            "counts_by_audience": by_audience,
        }

    def get_product_buyer_type(self, product_id: int) -> str | None:
        """单产品查询买家类型（默认受众用，不拉全部产品列表）。"""
        return self._session.scalar(
            select(ProductORM.buyer_type).where(ProductORM.id == product_id)
        )

    def company_detail(
        self,
        company_id: int,
        product_id: int | None = None,
        audience: str | None = None,
        bill_limit: int = 500,
    ) -> CompanyDetail | None:
        company = self._session.get(CompanyORM, company_id)
        if company is None:
            return None
        detail = CompanyDetail(
            company={
                "company_id": company.id,
                "name": (company.name_variants or [company.normalized_name])[0],
                "name_variants": list(company.name_variants or []),
                "normalized_name": company.normalized_name,
                "country": company.country,
                "city": company.city_guess or "",
                "address": company.address_guess or "",
                "same_name_conflict": bool(company.same_name_conflict),
                "website": company.website,
                "website_confirmed": bool(company.website_confirmed),
                "website_source": company.website_source or "",
                "website_confidence": company.website_confidence or "",
            }
        )

        score_stmt = select(CompanyScoreORM).where(CompanyScoreORM.company_id == company_id)
        if product_id:
            score_stmt = score_stmt.where(CompanyScoreORM.product_id == product_id)
        if audience:
            # both 产品两类受众的得分不串台：抽屉只展示当前受众
            score_stmt = score_stmt.where(CompanyScoreORM.audience == audience)
        for score in self._session.scalars(score_stmt.order_by(CompanyScoreORM.id)):
            detail.scores.append(
                {
                    "product_id": score.product_id,
                    "audience": score.audience,
                    "tier": score.tier,
                    "exclusion_code": score.exclusion_code,
                    "reasons": list(score.reasons or []),
                    "shipments": score.shipments,
                    "last_arrival": score.last_arrival,
                    "suppliers": list(score.suppliers or []),
                }
            )

        bills = list(
            self._session.scalars(
                select(RawBillORM)
                .where(
                    (RawBillORM.consignee_company_id == company_id)
                    | (RawBillORM.shipper_company_id == company_id)
                )
                .order_by(RawBillORM.arrival_date.desc(), RawBillORM.id.desc())
                .limit(bill_limit + 1)
            )
        )
        detail.bills_truncated = len(bills) > bill_limit
        for b in bills[:bill_limit]:
            detail.bills.append(
                {
                    "bill_id": b.id,
                    "arrival_date": b.arrival_date,
                    "hs_code": b.hs_code,
                    "hs_suspect": bool(b.hs_suspect),
                    "origin_country": b.origin_country,
                    "shipper": b.shipper_raw,
                    "consignee": b.consignee_raw,
                    "role": "shipper" if b.shipper_company_id == company_id else "consignee",
                    "product_description": b.product_description,
                    "port": b.port,
                    "bill_number": b.bill_number,
                    "quantity": b.quantity,
                }
            )
        return detail

    def product_name_and_primary_hs(self, product_id: int) -> tuple[str, str]:
        """发现买家任务用：产品名 + 第一个税号（可能都为空串）。"""
        from app.infrastructure.orm import ProductHsCodeORM, ProductORM

        name = (
            self._session.scalar(select(ProductORM.name).where(ProductORM.id == product_id)) or ""
        )
        hs = self._session.scalar(
            select(ProductHsCodeORM.hs_code)
            .where(ProductHsCodeORM.product_id == product_id)
            .order_by(ProductHsCodeORM.id)
            .limit(1)
        ) or ""
        return name, hs

    def suggest_hs_codes(self, keyword: str, limit: int = 8) -> list[tuple[str, int, str]]:
        """品名关键词 → (hs_code, shipments, sample_description)。"""
        from sqlalchemy import literal

        from app.infrastructure.orm import RawBillORM

        rows = self._session.execute(
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
        return [(hs, int(n), (sample or "")[:120]) for hs, n, sample in rows]

    def bill_count_for_hs(self, hs_code: str) -> int:
        from app.infrastructure.orm import RawBillORM

        return int(
            self._session.scalar(
                select(func.count()).select_from(RawBillORM).where(RawBillORM.hs_code == hs_code)
            )
            or 0
        )

    def iter_buyers(self, f: BuyerQueryFilters, batch_size: int = 500):
        """导出用：按批 yield BuyerRow，避免一次加载 10 万行。"""
        offset = 0
        while True:
            batch = BuyerQueryFilters(**{**f.__dict__, "limit": batch_size, "offset": offset})
            items, total = self.query_buyers(batch)
            if not items:
                return
            yield from items
            offset += len(items)
            if offset >= total or len(items) < batch_size:
                return

