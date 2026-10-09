"""DTO 映射：查询结果 → 接口模型（显式转换，不让内部结构漏到接口层）。"""

from __future__ import annotations

from app.infrastructure.queries import BuyerRow, CompanyDetail
from app.interface.schemas import (
    BuyerOut,
    CompanyBillOut,
    CompanyDetailOut,
    CompanyOut,
    CompanyScoreOut,
    ReasonOut,
)


def _reasons(payload: list[dict]) -> list[ReasonOut]:
    return [
        ReasonOut(
            code=item.get("code", ""),
            text=item.get("text", ""),
            bill_ids=list(item.get("bill_ids", [])),
        )
        for item in payload or []
    ]


def buyer_to_out(row: BuyerRow) -> BuyerOut:
    return BuyerOut(
        company_id=row.company_id,
        name=row.name,
        country=row.country,
        city=row.city,
        same_name_conflict=row.same_name_conflict,
        tier=row.tier,  # type: ignore[arg-type]
        exclusion_code=row.exclusion_code,
        shipments=row.shipments,
        last_arrival=row.last_arrival,
        suppliers=row.suppliers,
        reasons=_reasons(row.reasons),
    )


def company_detail_to_out(detail: CompanyDetail) -> CompanyDetailOut:
    return CompanyDetailOut(
        company=CompanyOut(**detail.company),
        scores=[
            CompanyScoreOut(
                product_id=s["product_id"],
                audience=s["audience"],
                tier=s["tier"],  # type: ignore[arg-type]
                exclusion_code=s.get("exclusion_code"),
                reasons=_reasons(s.get("reasons", [])),
                shipments=s.get("shipments", 0),
                last_arrival=s.get("last_arrival"),
                suppliers=list(s.get("suppliers", [])),
            )
            for s in detail.scores
        ],
        bills=[
            CompanyBillOut(
                bill_id=b["bill_id"],
                arrival_date=b["arrival_date"],
                hs_code=b["hs_code"],
                hs_suspect=b["hs_suspect"],
                origin_country=b["origin_country"],
                shipper=b["shipper"],
                consignee=b["consignee"],
                role=b["role"],
                product_description=b["product_description"],
                port=b["port"],
                bill_number=b["bill_number"],
                quantity=b["quantity"],
            )
            for b in detail.bills
        ],
    )
