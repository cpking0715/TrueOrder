"""启动前初始化：迁移到 head + 导入示例产品与非全量提单样本。幂等，可重复执行。

用法：uv run python -m app.bootstrap [--drop]
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.infrastructure.db import make_engine
from app.infrastructure.importers import CsvImporter
from app.infrastructure.orm import Base

SEED_DIR = Path(__file__).parent / "seed"
# 种子样本是按 2026-10 的滚动窗口设计的静态日期；固定基准日，避免随「今天」漂移
# 让演示分层与 sample_bills.README.md 的场景对照表失真。界面/API 导入不受影响。
SEED_AS_OF = date(2026, 10, 9)

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config(database_url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _ensure_schema(database_url: str) -> None:
    """建表走 Alembic；create_all 时代的旧库先 stamp 到基线再 upgrade，增量迁移照常执行。"""
    engine = make_engine(database_url)
    inspector = inspect(engine)
    has_tables = inspector.has_table("companies")
    has_alembic = inspector.has_table("alembic_version")
    engine.dispose()
    cfg = _alembic_config(database_url)
    if has_tables and not has_alembic:
        # 只标记「基线已建」：后续迁移（索引等）必须真实执行，不能直接跳到 head
        command.stamp(cfg, "df993f8cbfd2")
        print("检测到迁移前旧库，已标记基线，将执行增量迁移")
    command.upgrade(cfg, "head")
    print("schema 已就绪（alembic head）")


def main(drop: bool = False) -> None:
    settings = get_settings()
    database_url = settings.database_url
    if drop:
        # 仅允许样本/本机库：避免误清生产
        from sqlalchemy.engine import make_url

        localish = make_url(database_url).host in ("localhost", "127.0.0.1", "::1")
        if not settings.sample_mode or not localish:
            raise SystemExit(
                "--drop 已拒绝：仅当 TRUEORDER_SAMPLE_MODE=true 且数据库像是本机/样本库时可用"
            )
        engine = make_engine(database_url)
        Base.metadata.drop_all(engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()
        print("已删除全部表（--drop）")
    _ensure_schema(database_url)

    products_csv = (SEED_DIR / "products.csv").read_text(encoding="utf-8-sig")
    bills_csv = (SEED_DIR / "sample_bills.csv").read_text(encoding="utf-8-sig")

    with Session(make_engine(database_url)) as session:
        importer = CsvImporter(session)
        p = importer.import_products(products_csv, source="seed/products.csv")
        b, rescores = importer.import_bills(
            bills_csv, source_ref="seed/sample_bills.csv", as_of=SEED_AS_OF
        )

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
