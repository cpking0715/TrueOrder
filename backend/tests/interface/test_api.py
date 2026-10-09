"""接口层：路由、状态码、DTO 形状、CSV 导出。业务规则在领域/基础设施层已测。"""

from __future__ import annotations

from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[2] / "app" / "seed"
AS_OF = "2026-10-09"


def seed_via_api(client) -> dict:
    products_csv = (SEED_DIR / "products.csv").read_text(encoding="utf-8-sig")
    bills_csv = (SEED_DIR / "sample_bills.csv").read_text(encoding="utf-8-sig")
    r1 = client.post(
        "/api/products/import",
        files={"file": ("products.csv", products_csv, "text/csv")},
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        "/api/bills/import",
        files={"file": ("sample_bills.csv", bills_csv, "text/csv")},
        data={"as_of": AS_OF},
    )
    assert r2.status_code == 200, r2.text
    return {"products": r1.json(), "bills": r2.json()}


class TestMeta:
    def test_meta声明非全量样本(self, client):
        r = client.get("/api/meta")
        assert r.status_code == 200
        body = r.json()
        assert body["sample_mode"] is True
        assert "非全量" in body["sample_notice"]

    def test_health(self, client):
        assert client.get("/api/health").json() == {"status": "ok"}


class Test导入与产品列表:
    def test_完整导入流程(self, client):
        result = seed_via_api(client)
        assert result["products"]["products_upserted"] == 2
        assert result["bills"]["inserted_bills"] == 26
        assert result["bills"]["duplicate_bills"] == 0
        rescore = {r["product_code"]: r for r in result["bills"]["rescore"]}
        assert rescore["P-GARMENT"]["precise"] == 1
        assert rescore["P-GARMENT"]["excluded"] == 6
        assert rescore["P-BOARD"]["precise"] == 2

    def test_重复导入提单全部去重(self, client):
        seed_via_api(client)
        bills_csv = (SEED_DIR / "sample_bills.csv").read_text(encoding="utf-8-sig")
        r = client.post(
            "/api/bills/import",
            files={"file": ("sample_bills.csv", bills_csv, "text/csv")},
            data={"as_of": AS_OF},
        )
        body = r.json()
        assert body["inserted_bills"] == 0
        assert body["duplicate_bills"] == 26

    def test_产品列表带计数与税号(self, client):
        seed_via_api(client)
        products = client.get("/api/products").json()
        assert len(products) == 2
        board = [p for p in products if p["code"] == "P-BOARD"][0]
        assert board["buyer_type"] == "factory"
        assert board["hs_codes"][0]["hs_code"] == "480810"
        assert "纸箱" in board["hs_codes"][0]["note"]
        assert board["counts"]["precise"] == 2

    def test_非UTF8上传返回422(self, client):
        r = client.post(
            "/api/products/import",
            files={"file": ("products.csv", b"\xff\xfe\x00bad", "text/csv")},
        )
        assert r.status_code == 422

    def test_坏日期行被记录不中断导入(self, client):
        bad_csv = (
            "arrival_date,bill_number,consignee_name,consignee_address,consignee_country,"
            "shipper_name,shipper_address,shipper_country,origin_country,hs_code,"
            "product_description,port,quantity\n"
            "not-a-date,BOL-X,X LLC,\"\",US,Y CO,\"\",CN,CHINA,620462,TROUSERS,NY,1\n"
        )
        r = client.post(
            "/api/bills/import",
            files={"file": ("bad.csv", bad_csv, "text/csv")},
            data={"as_of": AS_OF},
        )
        body = r.json()
        assert r.status_code == 200
        assert body["inserted_bills"] == 0
        assert any("无法解析" in row for row in body["invalid_rows"])


class Test买家列表与导出:
    def test_默认受众跟随买家类型(self, client):
        seed_via_api(client)
        garment = [p for p in client.get("/api/products").json() if p["code"] == "P-GARMENT"][0]
        body = client.get(f"/api/products/{garment['product_id']}/buyers").json()
        assert body["audience"] == "importer"
        assert body["tier"] is None
        assert body["total"] >= 2

    def test_精准页签只回精准客户且理由带提单号(self, client):
        seed_via_api(client)
        garment = [p for p in client.get("/api/products").json() if p["code"] == "P-GARMENT"][0]
        body = client.get(
            f"/api/products/{garment['product_id']}/buyers", params={"tier": "precise"}
        ).json()
        assert body["total"] == 1
        buyer = body["items"][0]
        assert buyer["name"] == "BROOKLYN APPAREL LLC"
        assert buyer["shipments"] == 3
        codes = {reason["code"] for reason in buyer["reasons"]}
        assert {"RECENT_24M", "REPEAT_12M", "SUPPLIER_MATCH", "BUSINESS_MATCH"} <= codes
        supplier = [r for r in buyer["reasons"] if r["code"] == "SUPPLIER_MATCH"][0]
        assert supplier["bill_ids"]
        assert "HANGZHOU GARMENT" in supplier["text"]

    def test_全文检索参数q过滤(self, client):
        seed_via_api(client)
        board = [p for p in client.get("/api/products").json() if p["code"] == "P-BOARD"][0]
        body = client.get(
            f"/api/products/{board['product_id']}/buyers",
            params={"q": "packaging", "tier": "precise"},
        ).json()
        names = [i["name"] for i in body["items"]]
        assert "GREAT LAKES PACKAGING CORP" in names
        assert "ACME TRADING LLC" not in names

    def test_非法tier返回422(self, client):
        seed_via_api(client)
        r = client.get("/api/products/1/buyers", params={"tier": "vip"})
        assert r.status_code == 422

    def test_导出CSV表头与行数(self, client):
        seed_via_api(client)
        garment = [p for p in client.get("/api/products").json() if p["code"] == "P-GARMENT"][0]
        r = client.get(
            f"/api/products/{garment['product_id']}/buyers/export.csv",
            params={"tier": "precise"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        text = r.text.lstrip("\ufeff")
        lines = text.strip().splitlines()
        assert lines[0].split(",")[0] == "公司名"
        assert len(lines) == 2  # 表头 + 1 条精准
        assert "提单" in lines[1]  # 理由列点回提单号

    def test_导出尊重当前筛选(self, client):
        seed_via_api(client)
        board = [p for p in client.get("/api/products").json() if p["code"] == "P-BOARD"][0]
        r_all = client.get(f"/api/products/{board['product_id']}/buyers/export.csv")
        r_min = client.get(
            f"/api/products/{board['product_id']}/buyers/export.csv",
            params={"min_shipments": 3},
        )
        assert len(r_all.text.strip().splitlines()) > len(r_min.text.strip().splitlines())


class Test公司抽屉:
    def test_抽屉返回提单与得分(self, client):
        seed_via_api(client)
        garment = [p for p in client.get("/api/products").json() if p["code"] == "P-GARMENT"][0]
        precise = client.get(
            f"/api/products/{garment['product_id']}/buyers", params={"tier": "precise"}
        ).json()["items"][0]
        r = client.get(
            f"/api/companies/{precise['company_id']}", params={"product_id": garment["product_id"]}
        )
        assert r.status_code == 200
        detail = r.json()
        assert detail["company"]["country"] == "US"
        assert len(detail["bills"]) == 3
        assert {b["role"] for b in detail["bills"]} == {"consignee"}
        assert detail["scores"][0]["tier"] == "precise"
        assert detail["scores"][0]["suppliers"] == ["HANGZHOU GARMENT CO LTD"]

    def test_公司不存在返回404(self, client):
        assert client.get("/api/companies/99999").status_code == 404
