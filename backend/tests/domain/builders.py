"""领域测试共享的构造器：直接 new 领域实体，不经过任何 I/O。"""

from datetime import date

from app.domain.entities import (
    Audience,
    BillEvidence,
    CompanyFacts,
    HsAssignment,
    ProductConfig,
)

AS_OF = date(2026, 10, 9)

GARMENT_PRODUCT = ProductConfig(
    product_id=1,
    code="P-GARMENT",
    name="女士棉质长裤（成衣）",
    buyer_type="importer",
    hs_assignments=(HsAssignment(hs_code="620462", audience="importer"),),
    buyer_keywords=("APPAREL", "CLOTHING", "TRADING", "WHOLESALE", "FASHION"),
    peer_keywords=("GARMENT FACTORY", "APPAREL MANUFACTUR"),
)

BOARD_PRODUCT = ProductConfig(
    product_id=2,
    code="P-BOARD",
    name="瓦楞纸板（原纸）",
    buyer_type="factory",
    hs_assignments=(
        HsAssignment(hs_code="480810", audience="factory", note="原料税号，非纸箱成品 4819"),
    ),
    buyer_keywords=("PACKAGING", "CARTON", "CORRUGATED", "BOX", "PAPER", "CONVERT"),
    peer_keywords=("PAPER MILL", "BOARD MILL", "PULP"),
)


def bill(
    bill_id: int,
    arrival: date,
    hs: str = "620462",
    origin: str = "CN",
    shipper: str = "HANGZHOU GARMENT CO LTD",
    suspect: bool = False,
    description: str = "WOMENS COTTON TROUSERS",
) -> BillEvidence:
    from app.domain.normalize import normalize_company_name

    return BillEvidence(
        bill_id=bill_id,
        arrival_date=arrival,
        hs_code=hs,
        hs_suspect=suspect,
        origin_country=origin,
        shipper_name=shipper,
        shipper_normalized=normalize_company_name(shipper),
        product_description=description,
    )


def company(
    company_id: int = 101,
    name: str = "BROOKLYN APPAREL LLC",
    address: str = "350 FIFTH AVE, NEW YORK NY 10118, USA",
    country: str = "US",
    bills: tuple[BillEvidence, ...] = (),
    variants: tuple[str, ...] | None = None,
) -> CompanyFacts:
    from app.domain.normalize import normalize_company_name

    return CompanyFacts(
        company_id=company_id,
        normalized_name=normalize_company_name(name),
        name_variants=variants if variants is not None else (name,),
        address=address,
        country=country,
        bills=bills,
    )


def garment_audience() -> Audience:
    return "importer"
