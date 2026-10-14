"""端口实现：产品、企业池装载、得分写入（SQLAlchemy + PostgreSQL）。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities import (
    Audience,
    BillEvidence,
    CompanyFacts,
    HsAssignment,
    LeadSource,
    ProductConfig,
    ScoreReason,
    ScoreResult,
)
from app.domain.normalize import months_before, normalize_company_name
from app.infrastructure.orm import (
    CompanyLeadSourceORM,
    CompanyORM,
    CompanyScoreORM,
    OpportunityORM,
    ProductHsCodeORM,
    ProductORM,
    RawBillORM,
)


def _to_product_config(product: ProductORM, hs_rows: Sequence[ProductHsCodeORM]) -> ProductConfig:
    return ProductConfig(
        product_id=product.id,
        code=product.code,
        name=product.name,
        buyer_type=product.buyer_type,
        hs_assignments=tuple(
            HsAssignment(hs_code=r.hs_code, audience=r.audience, note=r.note or "") for r in hs_rows
        ),
        buyer_keywords=tuple(product.buyer_keywords or ()),
        peer_keywords=tuple(product.peer_keywords or ()),
        description=product.description or "",
    )


class SqlProductRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_products(self) -> list[ProductConfig]:
        products = list(self._session.scalars(select(ProductORM).order_by(ProductORM.id)))
        if not products:
            return []
        hs_rows = self._session.scalars(
            select(ProductHsCodeORM).where(
                ProductHsCodeORM.product_id.in_([p.id for p in products])
            )
        )
        by_product: dict[int, list[ProductHsCodeORM]] = defaultdict(list)
        for row in hs_rows:
            by_product[row.product_id].append(row)
        return [
            _to_product_config(p, sorted(by_product.get(p.id, []), key=lambda r: r.id))
            for p in products
        ]

    def get_product(self, product_id: int) -> ProductConfig | None:
        product = self._session.get(ProductORM, product_id)
        if product is None:
            return None
        hs_rows = self._session.scalars(
            select(ProductHsCodeORM)
            .where(ProductHsCodeORM.product_id == product_id)
            .order_by(ProductHsCodeORM.id)
        ).all()
        return _to_product_config(product, hs_rows)

    def next_quick_code(self) -> str:
        """快速建产品的编码：QUICK-0001 递增，不与既有 code 冲突。"""
        codes = self._session.scalars(
            select(ProductORM.code).where(ProductORM.code.like("QUICK-%"))
        )
        max_n = 0
        for code in codes:
            suffix = code.removeprefix("QUICK-")
            if suffix.isdigit():
                max_n = max(max_n, int(suffix))
        return f"QUICK-{max_n + 1:04d}"

    def find_quick_duplicate(self, name: str, hs_code: str, buyer_type: str) -> int | None:
        """同名同税号同受众的既有产品 id（快速建产品的重复判定）。"""
        row = self._session.execute(
            select(ProductORM.id)
            .join(ProductHsCodeORM, ProductHsCodeORM.product_id == ProductORM.id)
            .where(
                ProductORM.name == name,
                ProductORM.buyer_type == buyer_type,
                ProductHsCodeORM.hs_code == hs_code,
            )
        ).first()
        return int(row[0]) if row else None

    def create_quick(self, build) -> tuple[int, str | None]:
        """取号并插入快速产品；并发撞唯一编号时自动换号重试（最多 3 次）。

        build(code) 返回 (ProductConfig | None, 错误描述 | None)，与 build_quick_product 一致。
        """
        for attempt in range(3):
            product, error = build(self.next_quick_code())
            if error or product is None:
                return 0, error
            try:
                # SAVEPOINT：撞号只回滚本次插入，不波及外层事务里其他未提交改动
                with self._session.begin_nested():
                    return self.upsert_product(product), None
            except IntegrityError:
                if attempt == 2:
                    return 0, "产品编码冲突，请重试"
        return 0, "unreachable"

    def upsert_product(self, product: ProductConfig) -> int:
        """按 code 更新产品并整体替换税号对应关系（幂等）。"""
        existing = self._session.scalar(select(ProductORM).where(ProductORM.code == product.code))
        if existing is None:
            existing = ProductORM(
                code=product.code,
                name=product.name,
                description=product.description,
                buyer_type=product.buyer_type,
                buyer_keywords=list(product.buyer_keywords),
                peer_keywords=list(product.peer_keywords),
            )
            self._session.add(existing)
            self._session.flush()
        else:
            existing.name = product.name
            existing.description = product.description
            existing.buyer_type = product.buyer_type
            existing.buyer_keywords = list(product.buyer_keywords)
            existing.peer_keywords = list(product.peer_keywords)

        self._session.execute(
            delete(ProductHsCodeORM).where(ProductHsCodeORM.product_id == existing.id)
        )
        for hs in product.hs_assignments:
            self._session.add(
                ProductHsCodeORM(
                    product_id=existing.id,
                    hs_code=hs.hs_code,
                    audience=hs.audience,
                    note=hs.note,
                )
            )
        self._session.flush()
        return existing.id


class SqlBuyerPoolReader:
    """按税号族（4 位前缀）装载候选企业与其全部族内提单。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_pool(
        self, family_prefixes: Sequence[str], as_of: date, product_id: int | None = None
    ) -> list[CompanyFacts]:
        leads = self._lead_sources(product_id) if product_id is not None else {}
        bills: list[RawBillORM] = []
        if family_prefixes:
            window_start = months_before(as_of, 24)
            bills = list(
                self._session.scalars(
                    select(RawBillORM).where(
                        func.left(RawBillORM.hs_code, 4).in_(list(family_prefixes)),
                        RawBillORM.arrival_date >= window_start,
                    )
                )
            )
        if not bills and not leads:
            return []
        consignee_ids = {b.consignee_company_id for b in bills if b.consignee_company_id}
        shipper_ids = {b.shipper_company_id for b in bills if b.shipper_company_id}
        companies = {
            c.id: c
            for c in self._session.scalars(
                select(CompanyORM).where(
                    CompanyORM.id.in_(list(consignee_ids | shipper_ids | set(leads)))
                )
            )
        }

        facts_by_company: dict[int, list[BillEvidence]] = defaultdict(list)
        for b in bills:
            if not b.consignee_company_id:
                continue
            shipper_company = companies.get(b.shipper_company_id) if b.shipper_company_id else None
            shipper_normalized = (
                shipper_company.normalized_name
                if shipper_company is not None
                else normalize_company_name(b.shipper_raw)
            )
            facts_by_company[b.consignee_company_id].append(
                BillEvidence(
                    bill_id=b.id,
                    arrival_date=b.arrival_date,
                    hs_code=b.hs_code or "",
                    hs_suspect=bool(b.hs_suspect),
                    origin_country=b.origin_country or "",
                    shipper_name=b.shipper_raw or "",
                    shipper_normalized=shipper_normalized,
                    product_description=b.product_description or "",
                )
            )

        # 无合格税号提单、只有来源线索的企业也进池（打分层决定只入潜在层）
        for company_id in leads:
            facts_by_company.setdefault(company_id, [])

        result: list[CompanyFacts] = []
        for company_id, evidences in facts_by_company.items():
            company = companies.get(company_id)
            if company is None:
                continue
            result.append(
                CompanyFacts(
                    company_id=company.id,
                    normalized_name=company.normalized_name,
                    name_variants=tuple(company.name_variants or ()),
                    address=company.address_guess or "",
                    country=company.country,
                    bills=tuple(sorted(evidences, key=lambda e: (e.arrival_date, e.bill_id))),
                    lead_sources=tuple(leads.get(company_id, ())),
                )
            )
        return result

    def _lead_sources(self, product_id: int) -> dict[int, list[LeadSource]]:
        """该产品的非提单来源线索：AI 买家发现记录 + 已建商机（手动加入跟进）。"""
        out: dict[int, list[LeadSource]] = defaultdict(list)
        for company_id, source, ref in self._session.execute(
            select(
                CompanyLeadSourceORM.company_id,
                CompanyLeadSourceORM.source,
                CompanyLeadSourceORM.source_ref,
            ).where(CompanyLeadSourceORM.product_id == product_id)
        ):
            label = "AI 买家发现" if source == "ai_discover" else source
            out[company_id].append(LeadSource(kind=source, label=label, ref=ref or ""))
        for company_id, opp_id, stage in self._session.execute(
            select(OpportunityORM.company_id, OpportunityORM.id, OpportunityORM.stage).where(
                OpportunityORM.product_id == product_id,
                # 已流失＝用户判定不跟，不再作为线索
                OpportunityORM.stage != "lost",
            )
        ):
            out[company_id].append(
                LeadSource(
                    kind="opportunity", label=f"已加入跟进（{stage}）", ref=f"opportunity:{opp_id}"
                )
            )
        return out


class SqlScoreWriter:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_scores(self, product_id: int, results: Sequence[ScoreResult]) -> int:
        self._session.execute(
            delete(CompanyScoreORM).where(CompanyScoreORM.product_id == product_id)
        )
        for r in results:
            self._session.add(self._to_orm(r))
        self._session.flush()
        return len(results)

    @staticmethod
    def _to_orm(r: ScoreResult) -> CompanyScoreORM:
        return CompanyScoreORM(
            product_id=r.product_id,
            company_id=r.company_id,
            audience=r.audience,
            tier=r.tier,
            exclusion_code=r.exclusion_code,
            reasons=[
                {"code": reason.code, "text": reason.text, "bill_ids": list(reason.bill_ids)}
                for reason in r.reasons
            ],
            shipments=r.shipments,
            last_arrival=r.last_arrival,
            suppliers=list(r.suppliers),
        )


def reasons_from_json(payload: list[dict]) -> tuple[ScoreReason, ...]:
    return tuple(
        ScoreReason(
            code=i.get("code", ""),
            text=i.get("text", ""),
            bill_ids=tuple(i.get("bill_ids", [])),
        )
        for i in payload or []
    )


def audience_values(audience: Audience | str) -> list[str]:
    """受众参数归一：only importer / factory（both 产品在目录里拆成两类受众行）。"""
    return [audience]
