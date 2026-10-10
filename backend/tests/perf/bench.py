"""性能基准（WP0-4.4）：导入耗时、单产品打分耗时与峰值内存、买家列表 p95。

结果写入 docs/perf.md（人工整理），本脚本只输出机器可读的 JSON 行。
用法：uv run python tests/perf/bench.py --csv tests/perf/bills_100k.csv --label 100k
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


import argparse
import json
import time
import tracemalloc
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.domain.parse import build_quick_product
from app.infrastructure.importers import CsvImporter
from app.infrastructure.queries import BuyerQueryFilters, SqlBuyerQueries
from app.infrastructure.repositories import SqlProductRepository

ADMIN_URL = "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"
PERF_DB = "trueorder_perf"
PERF_URL = f"postgresql+psycopg://trueorder:trueorder@localhost:5433/{PERF_DB}"
AS_OF = date(2026, 10, 9)


def main() -> None:
    parser = argparse.ArgumentParser(description="性能基准")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {PERF_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {PERF_DB}"))
    admin.dispose()

    engine = create_engine(PERF_URL)
    from app.infrastructure.orm import Base

    Base.metadata.create_all(engine)
    csv_text = args.csv.read_text(encoding="utf-8-sig")

    result: dict = {"label": args.label, "rows": csv_text.count("\n") - 1}

    with Session(engine) as session:
        importer = CsvImporter(session)
        t0 = time.perf_counter()
        summary, _ = importer.import_bills(csv_text, as_of=AS_OF, rescore=False)
        result["import_seconds"] = round(time.perf_counter() - t0, 2)
        result["imported"] = summary.inserted_bills

        repo = SqlProductRepository(session)
        product_id, err = repo.create_quick(
            lambda code: build_quick_product(
                code=code, name="perf", hs_code="620462", buyer_type="importer",
                buyer_keywords=["SYNTHETIC"],
            )
        )
        assert err is None, err
        session.commit()

        tracemalloc.start()
        t0 = time.perf_counter()
        score = importer.rescore_one(product_id, AS_OF)
        result["rescore_seconds"] = round(time.perf_counter() - t0, 2)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result["rescore_peak_mb"] = round(peak / 1024 / 1024, 1)
        result["scored_companies"] = (
            score.potential + score.precise + score.excluded if score else 0
        )

        queries = SqlBuyerQueries(session)
        combos = {
            "q": BuyerQueryFilters(product_id=product_id, audience="importer", q="BUYER"),
            "country": BuyerQueryFilters(product_id=product_id, audience="importer", country="US"),
            "tier": BuyerQueryFilters(product_id=product_id, audience="importer", tier="potential"),
            "combined": BuyerQueryFilters(
                product_id=product_id, audience="importer", tier="potential", q="BUYER"
            ),
        }
        p95: dict[str, float] = {}
        for name, filters in combos.items():
            samples = []
            for _ in range(20):
                t0 = time.perf_counter()
                queries.query_buyers(filters)
                samples.append((time.perf_counter() - t0) * 1000)
            samples.sort()
            p95[name] = round(samples[int(len(samples) * 0.95) - 1], 1)
        result["list_p95_ms"] = p95

    engine.dispose()
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE {PERF_DB} WITH (FORCE)"))
    admin.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
