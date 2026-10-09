"""产品与买家路由：以产品为入口，潜在/精准两个视图，导出当前筛选。"""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import BuyerQueryFilters, SqlBuyerQueries
from app.interface.deps import get_buyer_queries, get_importer
from app.interface.mapping import buyer_to_out
from app.interface.schemas import BuyerListOut, ImportSummaryOut, ProductOut

router = APIRouter(prefix="/api/products", tags=["products"])


def _default_audience(queries: SqlBuyerQueries, product_id: int) -> str:
    products = queries.list_products_with_counts()
    for p in products:
        if p["product_id"] == product_id:
            if p["buyer_type"] in ("importer", "factory"):
                return p["buyer_type"]
            return "importer"  # both 产品由前端显式切换受众
    raise HTTPException(status_code=404, detail=f"产品 {product_id} 不存在")


@router.get("", response_model=list[ProductOut])
def list_products(queries: SqlBuyerQueries = Depends(get_buyer_queries)):
    return [
        ProductOut(
            product_id=p["product_id"],
            code=p["code"],
            name=p["name"],
            description=p["description"],
            buyer_type=p["buyer_type"],
            hs_codes=p["hs_codes"],  # type: ignore[arg-type]
            counts=p["counts"],
        )
        for p in queries.list_products_with_counts()
    ]


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

    buffer = io.StringIO()
    buffer.write("\ufeff")  # Excel 友好的 BOM
    writer = csv.writer(buffer)
    header = ["公司名", "国家", "城市", "等级", "票数", "最近到港", "供货方", "同名冲突", "排除原因", "得分理由"]  # noqa: E501
    writer.writerow(header)
    for buyer in items:
        writer.writerow(
            [
                buyer.name,
                buyer.country,
                buyer.city,
                buyer.tier,
                buyer.shipments,
                buyer.last_arrival or "",
                "; ".join(buyer.suppliers),
                "是" if buyer.same_name_conflict else "",
                buyer.exclusion_code or "",
                reason_text(buyer),
            ]
        )
    filename = f"buyers_product{product_id}_{audience}_{tier or 'all'}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=ImportSummaryOut)
async def import_products_csv(
    file: UploadFile,
    importer: CsvImporter = Depends(get_importer),
):
    """产品目录 CSV 导入：每行一个产品 + 税号 + 买家类型，多行税号自动合并。"""
    try:
        csv_text = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"CSV 必须是 UTF-8：{exc}") from exc
    summary = importer.import_products(csv_text, source=file.filename or "upload")
    # 产品目录变化可能影响既有得分（关键词），导入后重打分
    rescores = importer.rescore(date.today())
    return ImportSummaryOut(**summary.__dict__, rescore=[r.__dict__ for r in rescores])
