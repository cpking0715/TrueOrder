"""联系人路由（WP1）：手工/CSV 录入、编辑、标记不再联系、清除、官网字段、按买家筛选导出。"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.infrastructure.contact_repository import SqlContactRepository
from app.infrastructure.import_jobs import enqueue_import
from app.infrastructure.lead_sources import record_contact_leads
from app.infrastructure.queries import BuyerQueryFilters, SqlBuyerQueries
from app.interface.csv_safety import sanitize_csv_cell
from app.interface.deps import (
    CsvUpload,
    default_audience,
    get_buyer_queries,
    get_contact_repository,
    get_session,
    read_csv_upload,
)
from app.interface.schemas import (
    CompanyPatchIn,
    CompanyWebsiteOut,
    ContactCreateIn,
    ContactOut,
    ContactUpdateIn,
    ImportJobOut,
)

router = APIRouter(prefix="/api", tags=["contacts"])


def _to_out(row) -> ContactOut:
    return ContactOut(
        contact_id=row.contact_id,
        company_id=row.company_id,
        name=row.name,
        title=row.title,
        email=row.email,
        phone=row.phone,
        is_generic=row.is_generic,
        source=row.source,
        source_ref=row.source_ref,
        acquired_at=row.acquired_at,
        verify_status=row.verify_status,
        do_not_contact=row.do_not_contact,
    )


@router.get("/companies/{company_id}/contacts", response_model=list[ContactOut])
def list_contacts(
    company_id: int,
    repo: SqlContactRepository = Depends(get_contact_repository),
):
    if not repo.company_exists(company_id):
        raise HTTPException(status_code=404, detail=f"公司 {company_id} 不存在")
    return [_to_out(r) for r in repo.list_by_company(company_id)]


@router.post("/companies/{company_id}/contacts", response_model=ContactOut, status_code=201)
def add_contact(
    company_id: int,
    payload: ContactCreateIn,
    product_id: int | None = None,
    repo: SqlContactRepository = Depends(get_contact_repository),
    session: Session = Depends(get_session),
):
    """手动录入；带 product_id（从产品页抽屉添加）时记为该产品的 contact_manual 线索。"""
    if not repo.company_exists(company_id):
        raise HTTPException(status_code=404, detail=f"公司 {company_id} 不存在")
    result = repo.add(
        company_id,
        name=payload.name,
        title=payload.title,
        email=payload.email,
        phone=payload.phone,
        source="manual",
    )
    if result.error == "invalid_email":
        raise HTTPException(status_code=422, detail="邮箱格式非法")
    if result.error == "duplicate":
        raise HTTPException(status_code=409, detail={"message": "该公司已有此邮箱的联系人"})
    if product_id and record_contact_leads(session, product_id, company_id):
        session.commit()
    return _to_out(result.contact)


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: int,
    payload: ContactUpdateIn,
    repo: SqlContactRepository = Depends(get_contact_repository),
):
    result = repo.update(
        contact_id,
        name=payload.name,
        title=payload.title,
        email=payload.email,
        phone=payload.phone,
        do_not_contact=payload.do_not_contact,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"联系人 {contact_id} 不存在")
    if result == "duplicate":
        raise HTTPException(status_code=409, detail={"message": "该公司已有此邮箱的联系人"})
    if result == "invalid_email":
        raise HTTPException(status_code=422, detail="邮箱格式非法")
    return _to_out(result)


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(
    contact_id: int,
    repo: SqlContactRepository = Depends(get_contact_repository),
):
    """一键清除该联系人全部数据：第一期硬删行（活动表脱敏逻辑随第二期补）。"""
    if not repo.delete(contact_id):
        raise HTTPException(status_code=404, detail=f"联系人 {contact_id} 不存在")


@router.patch("/companies/{company_id}", response_model=CompanyWebsiteOut)
def patch_company(
    company_id: int,
    payload: CompanyPatchIn,
    repo: SqlContactRepository = Depends(get_contact_repository),
):
    result = repo.update_website(company_id, payload.website, payload.website_confirmed)
    if result is None:
        raise HTTPException(status_code=404, detail=f"公司 {company_id} 不存在")
    website, confirmed, source, confidence = result
    return CompanyWebsiteOut(company_id=company_id, website=website, website_confirmed=confirmed)


@router.post("/contacts/import", response_model=ImportJobOut, status_code=202)
def import_contacts_csv(
    upload: CsvUpload = Depends(read_csv_upload),
    session: Session = Depends(get_session),
):
    """联系人 CSV 导入（后台任务）：company_id 或「企业名+国家」定位企业。"""
    return ImportJobOut(job_id=enqueue_import(session, "contacts", upload.filename, upload.text))


@router.get("/products/{product_id}/contacts/export.csv")
def export_contacts(
    product_id: int,
    audience: str | None = None,
    tier: str | None = None,
    q: str | None = None,
    country: str | None = None,
    min_shipments: int | None = None,
    include_invalid: bool = False,
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
    repo: SqlContactRepository = Depends(get_contact_repository),
):
    """按买家列表同一组筛选导出联系人（每联系人一行）。

    默认排除 do_not_contact 与 verify_status in (invalid, bounced)；
    include_invalid=true 放开。按批拉买家，避免一次驻留 10 万行。
    """
    if audience is None:
        audience = default_audience(queries, product_id)
    if audience not in ("importer", "factory", "lead"):
        raise HTTPException(status_code=422, detail="audience 必须是 importer、factory 或 lead")
    filters = BuyerQueryFilters(
        product_id=product_id,
        audience=audience,
        tier=tier,
        q=q,
        country=country,
        min_shipments=min_shipments,
        limit=100000,
        offset=0,
    )

    def _row_line(values: list) -> str:
        buf = io.StringIO()
        csv.writer(buf).writerow(values)
        return buf.getvalue()

    def stream() -> Iterator[str]:
        yield "﻿"
        yield _row_line(
            [
                "公司名",
                "国家",
                "城市",
                "等级",
                "票数",
                "最近到港",
                "联系人姓名",
                "职位",
                "邮箱",
                "电话",
                "是否通用邮箱",
                "验证状态",
                "来源",
                "来源链接",
                "获取时间",
                "官网",
                "官网置信度",
            ]
        )
        batch: list = []
        for buyer in queries.iter_buyers(filters):
            batch.append(buyer)
            if len(batch) < 500:
                continue
            yield from _contact_rows(batch)
            batch = []
        if batch:
            yield from _contact_rows(batch)

    def _contact_rows(buyers: list) -> Iterator[str]:
        by_id = {b.company_id: b for b in buyers}
        for company_id, contact in repo.export_rows(list(by_id), include_invalid=include_invalid):
            buyer = by_id.get(company_id)
            if buyer is None:
                continue
            yield _row_line(
                [
                    sanitize_csv_cell(buyer.name),
                    sanitize_csv_cell(buyer.country),
                    sanitize_csv_cell(buyer.city),
                    sanitize_csv_cell(buyer.tier),
                    sanitize_csv_cell(buyer.shipments),
                    sanitize_csv_cell(buyer.last_arrival or ""),
                    sanitize_csv_cell(contact.name or ""),
                    sanitize_csv_cell(contact.title),
                    sanitize_csv_cell(contact.email or ""),
                    sanitize_csv_cell(contact.phone or ""),
                    sanitize_csv_cell("是" if contact.is_generic else ""),
                    sanitize_csv_cell(contact.verify_status),
                    sanitize_csv_cell(contact.source),
                    sanitize_csv_cell(contact.source_ref),
                    sanitize_csv_cell(contact.acquired_at.strftime("%Y-%m-%d")),
                    sanitize_csv_cell(contact.website or ""),
                    sanitize_csv_cell(contact.website_confidence or ""),
                ]
            )

    filename = f"contacts_product{product_id}_{audience}_{tier or 'all'}.csv"
    return StreamingResponse(
        stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
