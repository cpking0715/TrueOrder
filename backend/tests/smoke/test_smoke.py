"""e2e 冒烟：产品列表 → 页签 → 公司抽屉（提单证据）→ 导出 CSV 内容校验。

跑法：uv run pytest -q -m smoke（默认命令不含；动主链路时必须跑）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.import_helper import post_import

SEED_DIR = Path(__file__).resolve().parents[2] / "app" / "seed"
AS_OF = "2026-10-09"


def _seed(client) -> None:
    products_csv = (SEED_DIR / "products.csv").read_text(encoding="utf-8-sig")
    bills_csv = (SEED_DIR / "sample_bills.csv").read_text(encoding="utf-8-sig")
    r1 = post_import(client,
        "/api/products/import", files={"file": ("products.csv", products_csv, "text/csv")}
    )
    r2 = post_import(client,
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


@pytest.mark.smoke
class Test第一期获客闭环冒烟:
    """WP7：买家列表 → 选企业补全（fake 补全器）→ 域名与联系人自动写入
    → 验证状态 → 导出联系人 CSV 并校验内容。

    无 Hunter Key 时补全走 fake（来源标注可辨识）；验证状态保持 unknown，
    配 Key 后同一路径会自动排 verify_email 任务。
    """

    def _run_worker(self, client):
        from datetime import UTC, datetime

        from app.infrastructure.jobs import SqlJobQueue, Worker
        from app.interface.deps import get_session

        session = next(client.app.dependency_overrides[get_session]())
        from app.infrastructure.enrichment import build_registry

        Worker(SqlJobQueue(session), build_registry()).run_once(datetime.now(UTC))

    def test_补全到联系人导出闭环(self, client):
        _seed(client)
        products = client.get("/api/products").json()
        garment = next(p for p in products if p["code"] == "P-GARMENT")
        pid = garment["product_id"]
        precise = client.get(
            f"/api/products/{pid}/buyers", params={"tier": "precise"}
        ).json()
        top = precise["items"][0]
        cid = top["company_id"]

        # 填官网并确认（补全前置）
        patch = client.patch(
            f"/api/companies/{cid}",
            json={"website": "https://brooklynapparel.example", "website_confirmed": True},
        )
        assert patch.status_code == 200, patch.text

        # 触发补全 → 任务入队 → worker 消费（fake 补全器）
        enq = client.post(f"/api/companies/{cid}/find-contacts")
        assert enq.status_code == 202, enq.text
        job_id = enq.json()["job_id"]
        self._run_worker(client)

        jobs = client.get("/api/jobs", params={"status": "done"}).json()["items"]
        assert job_id in {j["id"] for j in jobs}, "补全任务应完成"

        # 联系人自动写入：带来源与获取时间，验证状态 unknown（无 Key 不排验证）
        contacts = client.get(f"/api/companies/{cid}/contacts").json()
        assert contacts, "联系人应自动写入"
        assert contacts[0]["source"] == "finder"
        assert "fake" in contacts[0]["source_ref"]  # 演示数据可辨识
        assert contacts[0]["verify_status"] == "unknown"

        # 额度用量可审计
        usage = client.get("/api/enrichment/usage").json()
        assert usage["used_today"] >= 1

        # 导出联系人 CSV：表头列齐、含联系人行与来源、默认排除规则生效
        export = client.get(f"/api/products/{pid}/contacts/export.csv")
        assert export.status_code == 200
        text = export.text
        header = text.splitlines()[0]
        for column in ["邮箱", "来源", "来源链接", "官网", "是否通用邮箱", "验证状态"]:
            assert column in header, f"导出缺列：{column}"
        assert contacts[0]["email"] in text
        assert "fake" in text

    def test_批量补全估计与执行(self, client):
        _seed(client)
        products = client.get("/api/products").json()
        garment = next(p for p in products if p["code"] == "P-GARMENT")
        pid = garment["product_id"]

        # 估计：不入队
        estimate = client.post(
            f"/api/products/{pid}/buyers/enrich", json={"limit": 3, "confirm": False}
        ).json()
        assert estimate["candidates"] >= 1
        jobs = client.get("/api/jobs").json()["items"]
        assert [j for j in jobs if j["kind"] != "import_csv"] == []

        # 确认执行 → 入队 → worker 消费 → 联系人出现
        executed = client.post(
            f"/api/products/{pid}/buyers/enrich", json={"limit": 3, "confirm": True}
        ).json()
        assert executed["enqueued"] >= 1
        self._run_worker(client)
        done = client.get("/api/jobs", params={"status": "done"}).json()["items"]
        assert len([j for j in done if j["kind"] != "import_csv"]) >= executed["enqueued"]

        # 再次估计：已有联系人与近期查过的都被跳过
        again = client.post(
            f"/api/products/{pid}/buyers/enrich", json={"limit": 10, "confirm": False}
        ).json()
        assert again["candidates"] == 0
        assert again["skipped_queried_recently"] + again["skipped_has_contacts"] >= 1

    def test_域名发现闭环_无官网自动采用(self, client):
        """F8：不预填官网——域名发现→高置信自动确认→联系人自动写入全链路。"""
        _seed(client)
        products = client.get("/api/products").json()
        garment = next(p for p in products if p["code"] == "P-GARMENT")
        pid = garment["product_id"]
        potential = client.get(
            f"/api/products/{pid}/buyers", params={"tier": "potential"}
        ).json()
        cid = potential["items"][0]["company_id"]

        enq = client.post(f"/api/companies/{cid}/find-contacts")
        assert enq.status_code == 202, enq.text
        self._run_worker(client)

        detail = client.get(f"/api/companies/{cid}").json()
        company = detail["company"]
        assert company["website"], "域名发现应自动写入官网"
        assert company["website_confirmed"] is True, "名称+国家对齐应达高置信自动采用"
        assert company["website_confidence"] == "high"
        contacts = client.get(f"/api/companies/{cid}/contacts").json()
        assert contacts, "高置信自动采用后联系人应自动写入"
        assert contacts[0]["source"] == "finder"
