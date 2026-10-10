"""SQLAlchemy 表结构（基础设施层，领域模型在 app.domain.entities）。

企业识别键：normalized_name + country（同名冲突只标记 same_name_conflict）。
全文检索：companies.search_vector 由 PG 生成列维护（simple 词典），GIN 索引。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProductORM(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    # importer / factory / both
    buyer_type: Mapped[str] = mapped_column(String(16))
    buyer_keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    peer_keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProductHsCodeORM(Base):
    __tablename__ = "product_hs_codes"
    __table_args__ = (
        UniqueConstraint("product_id", "hs_code", "audience", name="uq_product_hs_audience"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    hs_code: Mapped[str] = mapped_column(String(16), index=True)
    audience: Mapped[str] = mapped_column(String(16))  # importer / factory
    note: Mapped[str] = mapped_column(Text, default="")


class CompanyORM(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("normalized_name", "country", name="uq_company_name_country"),
        Index(
            "ix_companies_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_name: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(8))
    name_variants: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # 与 name_variants 平行：每个原始写法第一次出现时的地址（同名冲突判定用）
    variant_addresses: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    address_guess: Mapped[str] = mapped_column(Text, default="")
    city_guess: Mapped[str] = mapped_column(Text, default="")
    same_name_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    # 应用维护的检索源文本（name_variants + address + city）；
    # array_to_string 是 STABLE 不能进生成列，所以单独存一列。
    search_text: Mapped[str] = mapped_column(Text, default="")
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR(),
        Computed("to_tsvector('simple', coalesce(search_text, ''))", persisted=True),
    )
    # 官网（WP1）：来源与置信度两列随 WP4 补全功能一起迁移
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RawBillORM(Base):
    __tablename__ = "raw_bills"
    __table_args__ = (
        UniqueConstraint("bill_hash", name="uq_raw_bills_hash"),
        Index("ix_raw_bills_consignee", "consignee_company_id"),
        Index("ix_raw_bills_shipper", "shipper_company_id"),
        Index("ix_raw_bills_arrival", "arrival_date"),
        # 打分候选池按「税号 4 位前缀 + 到港窗口」过滤的复合表达式索引
        Index("ix_raw_bills_hs4_arrival", text("left(hs_code, 4)"), "arrival_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_ref: Mapped[str] = mapped_column(Text, default="")
    row_no: Mapped[int] = mapped_column(Integer, default=0)
    bill_hash: Mapped[str] = mapped_column(String(32))
    arrival_date: Mapped[date] = mapped_column(Date)
    consignee_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    consignee_raw: Mapped[str] = mapped_column(Text, default="")
    consignee_address: Mapped[str] = mapped_column(Text, default="")
    shipper_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    shipper_raw: Mapped[str] = mapped_column(Text, default="")
    shipper_address: Mapped[str] = mapped_column(Text, default="")
    hs_code: Mapped[str] = mapped_column(String(16), default="", index=True)
    hs_suspect: Mapped[bool] = mapped_column(Boolean, default=False)
    product_description: Mapped[str] = mapped_column(Text, default="")
    origin_country: Mapped[str] = mapped_column(String(8), default="")
    port: Mapped[str] = mapped_column(Text, default="")
    bill_number: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CompanyScoreORM(Base):
    __tablename__ = "company_scores"
    __table_args__ = (
        UniqueConstraint("product_id", "company_id", "audience", name="uq_scores_product_company"),
        Index("ix_scores_product_tier", "product_id", "tier"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    audience: Mapped[str] = mapped_column(String(16))
    tier: Mapped[str] = mapped_column(String(16))  # potential / precise / excluded
    exclusion_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # [{code, text, bill_ids: []}]
    reasons: Mapped[list[dict]] = mapped_column(JSON, default=list)
    shipments: Mapped[int] = mapped_column(Integer, default=0)
    last_arrival: Mapped[date | None] = mapped_column(Date, nullable=True)
    suppliers: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ContactORM(Base):
    """联系人（WP1）：来源可追溯，同公司同邮箱唯一（部分唯一索引），无邮箱可多条。"""

    __tablename__ = "contacts"
    __table_args__ = (
        # UNIQUE (company_id, lower(email)) WHERE email IS NOT NULL
        Index(
            "uq_contacts_company_email",
            "company_id",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        CheckConstraint(
            "source IN ('manual','csv','finder','website')", name="ck_contacts_source"
        ),
        CheckConstraint(
            "verify_status IN ('unknown','valid','invalid','bounced')",
            name="ck_contacts_verify_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_generic: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    source_ref: Mapped[str] = mapped_column(Text, default="")
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    verify_status: Mapped[str] = mapped_column(String(16), default="unknown")
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False)


class JobORM(Base):
    """后台任务（WP3）：基于 PostgreSQL 的队列，认领用 FOR UPDATE SKIP LOCKED。"""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','done','failed')", name="ck_jobs_status"
        ),
        CheckConstraint(
            "kind IN ('send_email','find_contacts','crawl_website','poll_imap')",
            name="ck_jobs_kind",
        ),
        # 认领路径只扫待跑任务
        Index(
            "ix_jobs_pending",
            "run_after",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
