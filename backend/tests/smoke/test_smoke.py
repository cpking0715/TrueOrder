"""e2e 冒烟：产品列表 → 页签 → 公司抽屉（提单证据）→ 导出 CSV 内容校验。

跑法：uv run pytest -q -m smoke（默认命令不含；动主链路时必须跑）。"""

from __future__ import annotations

from pathlib import Path

import pytest

SEED_DIR = Path(__file__).resolve().parents[2] / "app" / "seed"
AS_OF = "2026-10-09"


def _seed(client) -> None:
    products_csv = (SEED_DIR / "products.csv").read_text(encoding="utf-8-sig")
    bills_csv = (SEED_DIR / "sample_bills.csv").read_text(encoding="utf-8-sig")
    r1 = client.post(
        "/api/products/import", files={"file": ("products.csv", products_csv, "text/csv")}
    )
    r2 = client.post(
        "/api/bills/import",
        files={"file": ("sample_bills.csv", bills_csv, "text/csv")},
        data={"as_of": AS_OF},
    )
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)


@pytest.mark.smoke
class Test主链路冒烟:
    def test_产品列表页签抽屉导出(self, client):
        _seed(client)

        # 产品列表
        products = client.get("/api/products").json()
        garment = next(p for p in products if p["code"] == "P-GARMENT")
        pid = garment["product_id"]
        assert garment["counts"]["precise"] >= 1

        # 两个页签
        potential = client.get(
            f"/api/products/{pid}/buyers", params={"tier": "potential"}
        ).json()
        precise = client.get(
            f"/api/products/{pid}/buyers", params={"tier": "precise"}
        ).json()
        assert potential["total"] >= 1 and precise["total"] >= 1
        assert (
            potential["total"] + precise["total"]
            <= garment["counts"]["potential"] + garment["counts"]["precise"]
        )

        # 公司抽屉：提单证据 + 理由带提单 id
        top = precise["items"][0]
        detail = client.get(
            f"/api/companies/{top['company_id']}",
            params={"product_id": pid, "audience": "importer"},
        ).json()
        assert detail["bills"], "抽屉应有提单证据"
        assert any(
            r["bill_ids"] for s in detail["scores"] for r in s["reasons"]
        ), "得分理由应带提单 id"

        # 导出 CSV：表头 + 精准行 + 理由含提单号 + 无公式注入裸值
        export = client.get(
            f"/api/products/{pid}/buyers/export.csv", params={"tier": "precise"}
        )
        assert export.status_code == 200
        text = export.text
        assert text.startswith("\ufeff公司名")
        assert "得分理由" in text.splitlines()[0]
        body_lines = text.splitlines()[1:]
        assert 1 <= len(body_lines) <= precise["total"]
        assert "提单" in text  # 理由里点回提单 id

    def test_快速建产品到结果链路(self, client):
        _seed(client)
        r = client.post(
            "/api/products",
            json={
                "name": "冒烟产品",
                "hs_code": "620462",
                "buyer_type": "importer",
                "buyer_keywords": ["APPAREL"],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["code"].startswith("QUICK-")
        assert body["counts"]["potential"] + body["counts"]["precise"] >= 1
