"""合成提单生成器（性能评估用）：可配置行数，企业数约行数 1/20，税号集中在 5 个族。

用法：uv run python tests/perf/gen_bills.py --rows 100000 --out tests/perf/bills_100k.csv
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

HS_FAMILIES = ["620462", "480810", "847989", "611020", "732690"]
SHIPPER_POOL = [f"NINGBO MFG {i:03d} CO LTD" for i in range(50)]
BASE_DATE = date(2026, 10, 9)

HEADER = [
    "arrival_date", "bill_number", "consignee_name", "consignee_address",
    "consignee_country", "shipper_name", "shipper_address", "shipper_country",
    "origin_country", "hs_code", "product_description", "port", "quantity",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="生成合成提单 CSV")
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    companies = args.rows // 20
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for i in range(args.rows):
            buyer_no = rng.randrange(companies)
            arrival = BASE_DATE - timedelta(days=rng.randrange(730))
            writer.writerow(
                [
                    arrival.isoformat(),
                    f"BOL-{i:08d}",
                    f"OVERSEAS BUYER {buyer_no:06d} LLC",
                    f"{100 + buyer_no % 900} COMMERCE ST, CITY {buyer_no % 50}, USA",
                    "US",
                    rng.choice(SHIPPER_POOL),
                    "NO 88 RD, NINGBO, CN",
                    "CN",
                    rng.choice(["CN", "CN", "CN", "VN"]),
                    rng.choice(HS_FAMILIES),
                    "SYNTHETIC CARGO FOR PERF TEST",
                    rng.choice(["NEW YORK", "LOS ANGELES", "SAVANNAH", "HOUSTON"]),
                    str(rng.randrange(100, 20000)),
                ]
            )
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"已生成 {args.rows} 行 → {args.out}（{size_mb:.1f} MB，买家 {companies} 家）")


if __name__ == "__main__":
    main()
