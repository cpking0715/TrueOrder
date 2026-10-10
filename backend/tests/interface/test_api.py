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


class Test快速建产品:
    """「我填我的产品，帮我找客户」：先有提单数据，填产品立即出客户名单。"""

    def seed_bills_only(self, client) -> None:
        bills_csv = (SEED_DIR / "sample_bills.csv").read_text(encoding="utf-8-sig")
        r = client.post(
            "/api/bills/import",
            files={"file": ("sample_bills.csv", bills_csv, "text/csv")},
            data={"as_of": AS_OF},
        )
        assert r.status_code == 200, r.text

    def test_填产品立即出客户计数(self, client):
        self.seed_bills_only(client)
        r = client.post(
            "/api/products",
            json={
                "name": "女士棉质长裤",
                "hs_code": "620462",
                "buyer_type": "importer",
                "buyer_keywords": ["APPAREL", "CLOTHING"],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["code"].startswith("QUICK-")
        assert body["hs_codes"] == [{"hs_code": "620462", "audience": "importer", "note": ""}]
        assert body["counts"]["precise"] == 1  # BROOKLYN APPAREL（行业词命中业务匹配）
        assert body["counts"]["potential"] == 2

    def test_未填行业词时默认词只保潜在层(self, client):
        self.seed_bills_only(client)
        body = client.post(
            "/api/products",
            json={"name": "女士棉质长裤", "hs_code": "620462", "buyer_type": "importer"},
        ).json()
        assert body["counts"].get("precise", 0) == 0  # 默认词不含 APPAREL，精准层缺席
        assert body["counts"]["potential"] == 3

    def test_快速产品出现在列表且可查买家(self, client):
        self.seed_bills_only(client)
        product_id = client.post(
            "/api/products",
            json={
                "name": "瓦楞纸板",
                "hs_code": "480810",
                "buyer_type": "factory",
                "buyer_keywords": ["PACKAGING", "CARTON"],
            },
        ).json()["product_id"]
        names = [
            p["name"]
            for p in client.get(f"/api/products/{product_id}/buyers", params={"tier": "precise"}).json()["items"]
        ]
        assert "GREAT LAKES PACKAGING CORP" in names

    def test_重复提交生成不冲突编码(self, client):
        self.seed_bills_only(client)
        first = client.post(
            "/api/products", json={"name": "A", "hs_code": "620462", "buyer_type": "importer"}
        ).json()["code"]
        second = client.post(
            "/api/products", json={"name": "B", "hs_code": "620462", "buyer_type": "importer"}
        ).json()["code"]
        assert first != second

    def test_名称缺失返回422(self, client):
        r = client.post(
            "/api/products", json={"name": "  ", "hs_code": "620462", "buyer_type": "importer"}
        )
        assert r.status_code == 422
        assert "名称" in r.json()["detail"]

    def test_税号非法返回422(self, client):
        r = client.post(
            "/api/products", json={"name": "成衣", "hs_code": "62x462", "buyer_type": "importer"}
        )
        assert r.status_code == 422

    def test_买家词默认兜底可被覆盖(self, client):
        self.seed_bills_only(client)
        # 未填买家词：默认词命中 TRADING/WHOLESALE 类公司 → ACME TRADING 保持潜在层 BUSINESS_MATCH
        r = client.post(
            "/api/products",
            json={"name": "板", "hs_code": "480810", "buyer_type": "factory",
                  "buyer_keywords": ["PACKAGING"]},
        )
        assert r.status_code == 201
        product_id = r.json()["product_id"]
        buyers = client.get(
            f"/api/products/{product_id}/buyers", params={"tier": "potential"}
        ).json()["items"]
        assert any("UNION PACKAGING" in b["name"] for b in buyers)
        assert any(
            "PACKAGING" in reason["text"]
            for b in buyers
            for reason in b["reasons"]
            if reason["code"] == "BUSINESS_MATCH"
        )


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


BOTH_PRODUCTS_CSV = """code,name,description,buyer_type,hs_code,audience,note,buyer_keywords,peer_keywords
P-GARMENT,成衣,卖给进口商,importer,620462,importer,成衣税号,APPAREL;CLOTHING,GARMENT FACTORY
P-BOTH,面料与成衣,两者都卖,both,620462,importer,成衣受众,APPAREL;CLOTHING,
P-BOTH,面料与成衣,两者都卖,both,600632,factory,工厂受众,WEAVING;TEXTILE,
"""

BOTH_BILLS_CSV = """arrival_date,bill_number,consignee_name,consignee_address,consignee_country,shipper_name,shipper_address,shipper_country,origin_country,hs_code,product_description,port,quantity
2026-02-10,B1,SAIGON WEAVING MILL JSC,"LOT 5 VSIP, BINH DUONG, VN",US,JIANGSU FABRIC CO LTD,"NANTONG, CN",CN,CHINA,600632,"COTTON WOVEN FABRIC",LOS ANGELES,5000 KG
2026-06-15,B2,SAIGON WEAVING MILL JSC,"LOT 5 VSIP, BINH DUONG, VN",US,JIANGSU FABRIC CO LTD,"NANTONG, CN",CN,CHINA,600632,"COTTON WOVEN FABRIC",LOS ANGELES,4800 KG
2026-01-20,B3,MIDTOWN CLOTHING LLC,"200 W 40TH ST, NEW YORK NY 10018, USA",US,HANGZHOU GARMENT CO LTD,"HANGZHOU, CN",CN,CHINA,620462,"WOMENS COTTON TROUSERS",NEW YORK,700 CTNS
2026-04-20,B4,MIDTOWN CLOTHING LLC,"200 W 40TH ST, NEW YORK NY 10018, USA",US,HANGZHOU GARMENT CO LTD,"HANGZHOU, CN",CN,CHINA,620462,"WOMENS COTTON TROUSERS",NEW YORK,650 CTNS
"""


def seed_both_via_api(client) -> int:
    client.post(
        "/api/products/import",
        files={"file": ("products.csv", BOTH_PRODUCTS_CSV, "text/csv")},
    )
    client.post(
        "/api/bills/import",
        files={"file": ("bills.csv", BOTH_BILLS_CSV, "text/csv")},
        data={"as_of": AS_OF},
    )
    both = [p for p in client.get("/api/products").json() if p["code"] == "P-BOTH"][0]
    return both["product_id"]


class Test双受众产品:
    def test_产品计数按受众细分且总和兼容(self, client):
        both_id = seed_both_via_api(client)
        both = [p for p in client.get("/api/products").json() if p["product_id"] == both_id][0]
        # F5：counts_by_audience 分开，counts 保持总和（卡片用）
        assert both["counts_by_audience"] == {
            "importer": {"precise": 1},
            "factory": {"precise": 1},
        }
        assert both["counts"] == {"precise": 2}

    def test_抽屉得分按受众过滤(self, client):
        both_id = seed_both_via_api(client)
        importer_buyers = client.get(
            f"/api/products/{both_id}/buyers", params={"audience": "importer", "tier": "precise"}
        ).json()["items"]
        factory_buyers = client.get(
            f"/api/products/{both_id}/buyers", params={"audience": "factory", "tier": "precise"}
        ).json()["items"]
        assert [b["name"] for b in importer_buyers] == ["MIDTOWN CLOTHING LLC"]
        assert [b["name"] for b in factory_buyers] == ["SAIGON WEAVING MILL JSC"]

        weaving_id = factory_buyers[0]["company_id"]
        detail = client.get(
            f"/api/companies/{weaving_id}",
            params={"product_id": both_id, "audience": "factory"},
        ).json()
        # F5：只返回当前受众的得分，不再串台
        assert [s["audience"] for s in detail["scores"]] == ["factory"]
        assert detail["scores"][0]["tier"] == "precise"

        detail_all = client.get(f"/api/companies/{weaving_id}").json()
        assert len(detail_all["scores"]) == 1  # 该公司只在 factory 受众有得分


class Test建产品只打分新产品:
    def test_建新产品不重算既有产品得分(self, client, engine):
        """create_product 只打分新产品：既有产品的得分行 id 与 computed_at 不变。"""
        from sqlalchemy import text

        seed_via_api(client)
        with engine.connect() as conn:
            garment_id = conn.execute(
                text("select id from products where code = 'P-GARMENT'")
            ).scalar_one()
            before = conn.execute(
                text(
                    "select id, computed_at from company_scores "
                    "where product_id = :p order by id"
                ),
                {"p": garment_id},
            ).all()
        assert before, "种子导入后应有 P-GARMENT 得分"
        r = client.post(
            "/api/products",
            json={"name": "新查税号", "hs_code": "847989", "buyer_type": "importer"},
        )
        assert r.status_code == 201, r.text
        with engine.connect() as conn:
            after = conn.execute(
                text(
                    "select id, computed_at from company_scores "
                    "where product_id = :p order by id"
                ),
                {"p": garment_id},
            ).all()
        assert [row.id for row in before] == [row.id for row in after], "得分行被重建"
        assert [row.computed_at for row in before] == [row.computed_at for row in after]


class Test导出公式注入:
    def test_恶意公司名导出被转义(self, client):
        import csv
        import io

        seed_via_api(client)
        malicious = '=HYPERLINK("http://evil.example","click me")'
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "arrival_date", "bill_number", "consignee_name", "consignee_address",
                "consignee_country", "shipper_name", "shipper_address", "shipper_country",
                "origin_country", "hs_code", "product_description", "port", "quantity",
            ]
        )
        writer.writerow(
            [
                "2026-02-10", "BOL-EVIL", malicious, "1 EVIL ST, NY", "US",
                "HANGZHOU GARMENT CO LTD", "NO 66 RD, HANGZHOU, CN", "CN", "CHINA",
                "620462", "TROUSERS", "NEW YORK", "10",
            ]
        )
        bills_csv = buf.getvalue()
        r = client.post(
            "/api/bills/import",
            files={"file": ("evil.csv", bills_csv, "text/csv")},
            data={"as_of": AS_OF},
        )
        assert r.status_code == 200, r.text
        export = client.get("/api/products/1/buyers/export.csv", params={"audience": "importer"})
        assert export.status_code == 200
        text = export.text
        assert "'=HYPERLINK" in text, "恶意公司名未加前缀转义"


class Test上传上限:
    def test_超限上传返回413且库内无新增(self, client, engine):
        from sqlalchemy import text as sql_text

        from app.core.config import Settings, get_settings

        client.app.dependency_overrides[get_settings] = lambda: Settings(max_upload_mb=1)
        big = "x" * (1024 * 1024 + 1)
        r = client.post(
            "/api/bills/import",
            files={"file": ("big.csv", big, "text/csv")},
        )
        assert r.status_code == 413, r.text
        with engine.connect() as conn:
            count = conn.execute(sql_text("select count(*) from raw_bills")).scalar_one()
        assert count == 0


class Test建产品409与并发:
    def test_同名同税号同受众返回409带既有id(self, client):
        payload = {"name": "重复产品", "hs_code": "620462", "buyer_type": "importer"}
        first = client.post("/api/products", json=payload)
        assert first.status_code == 201, first.text
        again = client.post("/api/products", json=payload)
        assert again.status_code == 409, again.text
        assert again.json()["detail"]["product_id"] == first.json()["product_id"]




class Test产品详情:
    def test_产品详情返回单产品带计数(self, client):
        seed_via_api(client)
        r = client.get("/api/products/1")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["product_id"] == 1
        assert body["code"] == "P-GARMENT"
        assert body["counts"]["precise"] >= 1
        assert any(h["hs_code"] == "620462" for h in body["hs_codes"])

    def test_产品不存在404(self, client):
        assert client.get("/api/products/99999").status_code == 404
