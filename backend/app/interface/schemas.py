"""接口层 DTO（与领域实体、表结构分离，显式映射见 mapping.py）。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

Tier = Literal["potential", "precise", "excluded"]


class MetaOut(BaseModel):
    sample_mode: bool
    sample_notice: str


class ImportSummaryOut(BaseModel):
    inserted_bills: int = 0
    duplicate_bills: int = 0
    suspect_hs_bills: int = 0
    invalid_rows: list[str] = []
    companies_created: int = 0
    companies_updated: int = 0
    products_upserted: int = 0
    hs_assignments_written: int = 0
    rescore: list[dict] = []


class HsCodeOut(BaseModel):
    hs_code: str
    audience: str
    note: str = ""


class ProductOut(BaseModel):
    product_id: int
    code: str
    name: str
    description: str
    buyer_type: str
    hs_codes: list[HsCodeOut]
    counts: dict[str, int]
    # F5：both 产品两类受众的 tier 计数分开，避免页签数字串台
    counts_by_audience: dict[str, dict[str, int]] = {}


class ReasonOut(BaseModel):
    code: str
    text: str
    bill_ids: list[int]


class BuyerOut(BaseModel):
    company_id: int
    name: str
    country: str
    city: str
    same_name_conflict: bool
    tier: Tier
    exclusion_code: str | None = None
    shipments: int
    last_arrival: date | None = None
    suppliers: list[str]
    reasons: list[ReasonOut]


class BuyerListOut(BaseModel):
    items: list[BuyerOut]
    total: int
    audience: str
    tier: str | None
    q: str | None


class CompanyBillOut(BaseModel):
    bill_id: int
    arrival_date: date
    hs_code: str
    hs_suspect: bool
    origin_country: str
    shipper: str
    consignee: str
    role: str
    product_description: str
    port: str
    bill_number: str
    quantity: str


class CompanyScoreOut(BaseModel):
    product_id: int
    audience: str
    tier: Tier
    exclusion_code: str | None = None
    reasons: list[ReasonOut]
    shipments: int
    last_arrival: date | None = None
    suppliers: list[str]


class CompanyOut(BaseModel):
    company_id: int
    name: str
    name_variants: list[str]
    normalized_name: str
    country: str
    city: str
    address: str
    same_name_conflict: bool


class CompanyDetailOut(BaseModel):
    company: CompanyOut
    scores: list[CompanyScoreOut]
    bills: list[CompanyBillOut]
