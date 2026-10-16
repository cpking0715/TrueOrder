"""出海包 v0.1（内部工具）表结构：复用 products/companies/contacts，只加扩展表。

由 orm.py 末尾导入，保证 Base.metadata（Alembic/测试 create_all）包含这些表。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.orm import Base


class KitTaskProgressORM(Base):
    """14 天任务勾选进度（单用户内部工具，按任务键一行）。"""

    __tablename__ = "kit_task_progress"

    task_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KitProductProfileORM(Base):
    """产品档案：既有 products 的 1:1 扩展（主推款最多 5 个，由领域规则把关）。"""

    __tablename__ = "kit_product_profiles"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    image_url: Mapped[str] = mapped_column(Text, default="")
    specs: Mapped[str] = mapped_column(Text, default="")
    moq: Mapped[int] = mapped_column(Integer, default=1)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=30)
    selling_points: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    featured: Mapped[bool] = mapped_column(Boolean, default=True)


class KitBuyerTagORM(Base):
    """买家线索标签：既有 companies 的扩展（国家在 companies 上，这里存渠道与阶段）。"""

    __tablename__ = "kit_buyer_tags"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('new','contacted','replied','inquiry')", name="ck_kit_buyer_stage"
        ),
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    channel: Mapped[str] = mapped_column(String(16), default="email")
    stage: Mapped[str] = mapped_column(String(16), default="new")
    source_ref: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KitDraftORM(Base):
    """开发信草稿快照：只生成、不发送（无发送状态字段）。"""

    __tablename__ = "kit_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))  # llm / template
    follow_up_on: Mapped[list[date]] = mapped_column(ARRAY(Date), default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KitInquiryORM(Base):
    """询盘与报价：单行报价（v0.1 只支持一个产品一行）。"""

    __tablename__ = "kit_inquiries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new','quoted','sample','won','lost')", name="ck_kit_inquiry_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="new")
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
