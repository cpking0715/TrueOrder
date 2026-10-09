"""启动前初始化：建表 + 导入示例产品与非全量提单样本。幂等，可重复执行。

用法：uv run python -m app.bootstrap [--drop]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.db import make_engine
from app.infrastructure.importers import CsvImporter
from app.infrastructure.orm import Base

SEED_DIR = Path(__file__).parent / "seed"


def main(drop: bool = False) -> None:
    engine = make_engine(get_settings().database_url)
    if drop:
        Base.metadata.drop_all(engine)
        print("已删除全部表（--drop）")
    Base.metadata.create_all(engine)
    print("schema 已就绪")

    products_csv = (SEED_DIR / "products.csv").read_text(encoding="utf-8-sig")
    bills_csv = (SEED_DIR / "sample_bills.csv").read_text(encoding="utf-8-sig")

    with Session(engine) as session:
        importer = CsvImporter(session)
        p = importer.import_products(products_csv, source="seed/products.csv")
        b, rescores = importer.import_bills(bills_csv, source_ref="seed/sample_bills.csv")

    print(
        f"产品导入：{p.products_upserted} 个产品，{p.hs_assignments_written} 条税号对应，"
        f"非法行 {len(p.invalid_rows)}"
    )
    for bad in p.invalid_rows:
        print(f"  - {bad}")
    print(
        f"提单导入：新增 {b.inserted_bills} 票，重复 {b.duplicate_bills} 票，"
        f"税号可疑 {b.suspect_hs_bills} 票，新建企业 {b.companies_created} 家，"
        f"更新企业 {b.companies_updated} 家，非法行 {len(b.invalid_rows)}"
    )
    for bad in b.invalid_rows:
        print(f"  - {bad}")
    for r in rescores:
        print(
            f"打分：{r.product_code}（{','.join(r.audiences)}）"
            f" 潜在 {r.potential} / 精准 {r.precise} / 排除 {r.excluded}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TrueOrder 初始化")
    parser.add_argument("--drop", action="store_true", help="先删除全部表再重建")
    args = parser.parse_args()
    main(drop=args.drop)
