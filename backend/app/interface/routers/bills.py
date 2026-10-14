"""提单与公司路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException

from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import SqlBuyerQueries
from app.interface.deps import CsvUpload, get_buyer_queries, get_importer, read_csv_upload
from app.interface.mapping import company_detail_to_out
from app.interface.schemas import CompanyDetailOut, ImportSummaryOut

router = APIRouter(prefix="/api", tags=["bills", "companies"])


@router.post("/bills/import", response_model=ImportSummaryOut)
def import_bills_csv(
    upload: CsvUpload = Depends(read_csv_upload),
    as_of: date | None = Form(default=None),
    importer: CsvImporter = Depends(get_importer),
):
    """提单 CSV 导入：企业归并 + 去重 + 自动重打分。as_of 缺省用今天。"""
    summary, rescores = importer.import_bills(
        upload.text, source_ref=upload.filename, as_of=as_of
    )
    return ImportSummaryOut(**summary.__dict__, rescore=[r.__dict__ for r in rescores])


@router.get("/companies/{company_id}", response_model=CompanyDetailOut)
def company_detail(
    company_id: int,
    product_id: int | None = None,
    audience: str | None = None,
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
):
    """公司抽屉：票据、得分理由（带提单 id）、供货方。audience 过滤 both 产品的受众得分。"""
    detail = queries.company_detail(company_id, product_id=product_id, audience=audience)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"公司 {company_id} 不存在")
    return company_detail_to_out(detail)
