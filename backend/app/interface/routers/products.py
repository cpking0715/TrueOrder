"""产品与买家路由：以产品为入口，潜在/精准两个视图，导出当前筛选。"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.domain.parse import build_quick_product
from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import BuyerQueryFilters, SqlBuyerQueries
from app.infrastructure.repositories import SqlProductRepository
from app.interface.csv_safety import sanitize_csv_cell
from app.interface.deps import get_buyer_queries, get_importer, get_product_repository
from app.interface.mapping import buyer_to_out, product_row_to_out
from app.interface.schemas import (
    BuyerListOut,
    ImportSummaryOut,
    ProductCreateIn,
    ProductOut,
)

router = APIRouter(prefix="/api/products", tags=["products"])


def _default_audience(queries: SqlBuyerQueries, product_id: int) -> str:
    buyer_type = queries.get_product_buyer_type(product_id)
    if buyer_type is None:
        raise HTTPException(status_code=404, detail=f"产品 {product_id} 不存在")
    if buyer_type in ("importer", "factory"):
        return buyer_type
    return "importer"  # both 产品由前端显式切换受众


@router.get("", response_model=list[ProductOut])
def list_products(queries: SqlBuyerQueries = Depends(get_buyer_queries)):
    return [product_row_to_out(p) for p in queries.list_products_with_counts()]


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreateIn,
    repo: SqlProductRepository = Depends(get_product_repository),
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
    importer: CsvImporter = Depends(get_importer),
):
    """「填产品找客户」：建产品并立即在已导入提单库上打分，返回带计数的完整产品。"""
    duplicate_id = repo.find_quick_duplicate(
        payload.name.strip(), payload.hs_code.strip(), payload.buyer_type
    )
    if duplicate_id is not None:
        raise HTTPException(
            status_code=409,
            detail={"message": "同名同税号同受众的产品已存在", "product_id": duplicate_id},
        )
    product_id, quick_error = repo.create_quick(
        lambda code: build_quick_product(
            code=code,
            name=payload.name,
            hs_code=payload.hs_code,
            buyer_type=payload.buyer_type,
            description=payload.description,
            buyer_keywords=payload.buyer_keywords,
            peer_keywords=payload.peer_keywords,
        )
    )
    if quick_error or product_id == 0:
        raise HTTPException(status_code=422, detail=quick_error or "产品创建失败")
    importer.rescore_one(product_id, date.today())
    row = next(
        (p for p in queries.list_products_with_counts() if p["product_id"] == product_id), None
    )
    if row is None:
        raise HTTPException(status_code=500, detail="产品已创建但查询计数失败")
    return product_row_to_out(row)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
):
    row = queries.get_product_with_counts(product_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"产品 {product_id} 不存在")
    return product_row_to_out(row)


@router.get("/{product_id}/buyers", response_model=BuyerListOut)
def list_buyers(
    product_id: int,
    audience: str | None = None,
    tier: str | None = Query(default=None, pattern="^(potential|precise|excluded)$"),
    q: str | None = None,
    country: str | None = None,
    min_shipments: int | None = Query(default=None, ge=1),
    order: str = Query(default="shipments", pattern="^(shipments|last_arrival|name)$"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
):
    if audience is None:
        audience = _default_audience(queries, product_id)
    if audience not in ("importer", "factory"):
        raise HTTPException(status_code=422, detail="audience 必须是 importer 或 factory")
    filters = BuyerQueryFilters(
        product_id=product_id,
        audience=audience,
        tier=tier,
        q=q,
        country=country,
        min_shipments=min_shipments,
        order=order,
        limit=limit,
        offset=offset,
    )
    items, total = queries.query_buyers(filters)
    return BuyerListOut(
        items=[buyer_to_out(i) for i in items],
        total=total,
        audience=audience,
        tier=tier,
        q=q,
    )


@router.get("/{product_id}/buyers/export.csv")
def export_buyers(
    product_id: int,
    audience: str | None = None,
    tier: str | None = Query(default=None, pattern="^(potential|precise|excluded)$"),
    q: str | None = None,
    country: str | None = None,
    min_shipments: int | None = Query(default=None, ge=1),
    order: str = Query(default="shipments", pattern="^(shipments|last_arrival|name)$"),
    queries: SqlBuyerQueries = Depends(get_buyer_queries),
):
    """当前筛选导出 CSV（与列表同一查询，不分页）。"""
    if audience is None:
        audience = _default_audience(queries, product_id)
    if audience not in ("importer", "factory"):
        raise HTTPException(status_code=422, detail="audience 必须是 importer 或 factory")
    filters = BuyerQueryFilters(
        product_id=product_id,
        audience=audience,
        tier=tier,
        q=q,
        country=country,
        min_shipments=min_shipments,
        order=order,
        limit=100000,
        offset=0,
    )
    items, _ = queries.query_buyers(filters)

    def reason_text(buyer) -> str:
        return "；".join(
            f"{r['text']}（提单 {'/'.join(str(i) for i in r.get('bill_ids', []))}）"
            for r in buyer.reasons
        )

    def _row(values: list) -> str:
        buf = io.StringIO()
        csv.writer(buf).writerow(values)
        return buf.getvalue()

    def stream() -> Iterator[str]:
        yield "\ufeff"  # Excel 友好的 BOM
        yield _row(
            ["公司名", "国家", "城市", "等级", "票数", "最近到港", "供货方", "同名冲突", "排除原因", "得分理由"]  # noqa: E501
        )
        for buyer in items:
            yield _row(
                [
                    sanitize_csv_cell(buyer.name),
                    sanitize_csv_cell(buyer.country),
                    sanitize_csv_cell(buyer.city),
                    sanitize_csv_cell(buyer.tier),
                    sanitize_csv_cell(buyer.shipments),
                    sanitize_csv_cell(buyer.last_arrival or ""),
                    sanitize_csv_cell("; ".join(buyer.suppliers)),
                    sanitize_csv_cell("是" if buyer.same_name_conflict else ""),
                    sanitize_csv_cell(buyer.exclusion_code or ""),
                    sanitize_csv_cell(reason_text(buyer)),
                ]
            )

    filename = f"buyers_product{product_id}_{audience}_{tier or 'all'}.csv"
    return StreamingResponse(
        stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=ImportSummaryOut)
async def import_products_csv(
    file: UploadFile,
    request: Request,
    importer: CsvImporter = Depends(get_importer),
    settings: Settings = Depends(get_settings),
):
    """产品目录 CSV 导入：每行一个产品 + 税号 + 买家类型，多行税号自动合并。"""
    limit = settings.max_upload_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared is not None and int(declared) > limit:
        raise HTTPException(
            status_code=413, detail=f"文件超过上传上限 {settings.max_upload_mb} MB"
        )
    data = await file.read()
    if len(data) > limit:
        raise HTTPException(
            status_code=413, detail=f"文件超过上传上限 {settings.max_upload_mb} MB"
        )
    try:
        csv_text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"CSV 必须是 UTF-8：{exc}") from exc
    summary = importer.import_products(csv_text, source=file.filename or "upload")
    # 产品目录变化可能影响既有得分（关键词），导入后重打分
    rescores = importer.rescore(date.today())
    return ImportSummaryOut(**summary.__dict__, rescore=[r.__dict__ for r in rescores])
