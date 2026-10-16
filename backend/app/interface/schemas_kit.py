"""出海包 v0.1 接口 DTO（与领域实体、表结构分离，路由里显式映射）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class KitTaskOut(BaseModel):
    key: str
    day: int
    title: str
    page: str
    done: bool


class KitTasksOut(BaseModel):
    today: int
    done_count: int
    total: int
    tasks: list[KitTaskOut]


class KitTaskDoneIn(BaseModel):
    done: bool


class KitProfileIn(BaseModel):
    image_url: str = ""
    specs: str = ""
    moq: int = 1
    lead_time_days: int = 30
    selling_points: list[str] = []
    featured: bool = True


class KitProfileOut(BaseModel):
    product_id: int
    code: str
    name: str
    has_profile: bool
    image_url: str = ""
    specs: str = ""
    moq: int = 0
    lead_time_days: int = 0
    selling_points: list[str] = []
    featured: bool = False


class KitBuyerImportOut(BaseModel):
    rows_valid: int
    companies_created: int
    buyers_tagged: int
    already_in_library: int
    contacts_added: int
    duplicates_in_file: int
    errors: list[str]


class KitBuyerOut(BaseModel):
    company_id: int
    name: str
    country: str
    channel: str
    stage: str
    contact_id: int | None
    contact_name: str
    email: str | None


class KitBuyerPatchIn(BaseModel):
    channel: str | None = None
    stage: str | None = None


class KitDraftIn(BaseModel):
    product_id: int
    company_id: int
    contact_id: int | None = None
    channel: Literal["email", "whatsapp"] = "email"


class KitDraftOut(BaseModel):
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
    next_follow_up: date | None
    sent: bool = Field(False, description="恒为 false：出海包只生成草稿，从不发送")


class KitInquiryIn(BaseModel):
    company_id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    currency: str = "USD"
    note: str = ""


class KitInquiryPatchIn(BaseModel):
    status: Literal["new", "quoted", "sample", "won", "lost"]


class KitInquiryOut(BaseModel):
    id: int
    company_id: int
    company_name: str
    product_id: int
    product_name: str
    status: str
    status_label: str
    quantity: int
    unit_price: Decimal
    currency: str
    total: Decimal
    note: str
