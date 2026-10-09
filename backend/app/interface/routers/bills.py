"""提单与公司路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import SqlBuyerQueries
from app.interface.deps import get_buyer_queries, get_importer
from app.interface.mapping import company_detail_to_out
from app.interface.schemas import CompanyDetailOut, ImportSummaryOut

router = APIRouter(prefix="/api", tags=["bills", "companies"])


@router.post("/bills/import", response_model=ImportSummaryOut)
async def import_bills_csv(
    file: UploadFile,
    as_of: date | None = Form(default=None),
    importer: CsvImporter = Depends(get_importer),
):
    """提单 CSV 导入：企业归并 + 去重 + 自动重打分。as_of 缺省用今天。"""
    try:
        csv_text = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"CSV 必须是 UTF-8：{exc}") from exc
    summary, rescores = importer.import_bills(
        csv_text, source_ref=file.filename or "upload", as_of=as_of
    )
    return ImportSummaryOut(**summary.__dict__, rescore=[r.__dict__ for r in rescores])


@router.get("/companies/{company_id}", response_model=CompanyDetailOut)
def company_detail(
    company_id: int,
    product_id: int | None = None,
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
):
    """公司抽屉：票据、得分理由（带提单 id）、供货方。"""
    detail = queries.company_detail(company_id, product_id=product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"公司 {company_id} 不存在")
    return company_detail_to_out(detail)
