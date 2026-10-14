"""WP4 接口：单公司补全入队、批量估计与确认、官网确认、额度用量。"""

from __future__ import annotations

import pytest

from app.infrastructure.orm import CompanyORM, ContactORM
from tests.import_helper import post_import


@pytest.fixture()
def company_with_contacts(client) -> tuple[int, int]:
    """(无联系人公司 id, 有联系人公司 id)。经 override 的共享会话造数。"""
    from app.interface.deps import get_session

    session = next(client.app.dependency_overrides[get_session]())
    bare = CompanyORM(normalized_name="BARE CO", country="US", name_variants=["Bare Co"])
    withc = CompanyORM(normalized_name="WITHC CO", country="US", name_variants=["Withc Co"])
    session.add_all([bare, withc])
    session.flush()
    session.add(ContactORM(company_id=withc.id, title="", email="a@withc.com", source="manual"))
    session.commit()
    return bare.id, withc.id


class Test单公司补全:
    def test_入队返回任务id并可见于任务列表(self, client, company_with_contacts):
        bare_id, _ = company_with_contacts
        r = client.post(f"/api/companies/{bare_id}/find-contacts")
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["kind"] == "find_contacts"
        jobs = client.get("/api/jobs", params={"status": "pending"}).json()["items"]
        assert body["job_id"] in {j["id"] for j in jobs}

    def test_带product_id写入任务payload(self, client, company_with_contacts):
        bare_id, _ = company_with_contacts
        body = client.post(f"/api/companies/{bare_id}/find-contacts?product_id=5").json()
        job = client.get(f"/api/jobs/{body['job_id']}").json()
        assert job["payload"] == {"company_id": bare_id, "product_id": 5}

    def test_website方式入队抓取任务(self, client, company_with_contacts):
        bare_id, _ = company_with_contacts
        body = client.post(f"/api/companies/{bare_id}/find-contacts?method=website").json()
        assert body["kind"] == "crawl_website"

    def test_非法method返回422(self, client, company_with_contacts):
        bare_id, _ = company_with_contacts
        assert (
            client.post(f"/api/companies/{bare_id}/find-contacts?method=phone").status_code == 422
        )

    def test_公司不存在404(self, client):
        assert client.post("/api/companies/99999/find-contacts").status_code == 404


class Test官网确认与用量:
    def test_确认候选官网(self, client, company_with_contacts):
        bare_id, _ = company_with_contacts
        from app.interface.deps import get_session

        session = next(client.app.dependency_overrides[get_session]())
        company = session.get(CompanyORM, bare_id)
        company.website = "https://maybe.com"
        company.website_confidence = "medium"
        session.commit()

        body = client.post(f"/api/companies/{bare_id}/website/confirm").json()
        assert body["website_confirmed"] is True
        assert body["website_confidence"] == "medium"

    def test_用量端点(self, client):
        body = client.get("/api/enrichment/usage").json()
        assert body["daily_cap"] == 20
        assert body["configured"] in (True, False)
        assert body["remaining"] == body["daily_cap"] - body["used_today"]


class Test批量补全:
    def seed_product_with_buyers(self, client) -> int:
        """造一个产品与两票买家（潜在/精准各一）——复用种子导入。"""
        from pathlib import Path

        seed = Path(__file__).resolve().parents[2] / "app" / "seed"
        post_import(client,
            "/api/products/import",
            files={
                "file": ("p.csv", (seed / "products.csv").read_text("utf-8-sig"), "text/csv")
            },
        )
        post_import(client,
            "/api/bills/import",
            files={
                "file": (
                    "b.csv", (seed / "sample_bills.csv").read_text("utf-8-sig"), "text/csv"
                )
            },
            data={"as_of": "2026-10-09"},
        )
        garment = [p for p in client.get("/api/products").json() if p["code"] == "P-GARMENT"][0]
        return garment["product_id"]

    def test_不带confirm只返回估计不入队(self, client):
        product_id = self.seed_product_with_buyers(client)
        r = client.post(
            f"/api/products/{product_id}/buyers/enrich",
            json={"limit": 10, "confirm": False},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enqueued"] == 0 if "enqueued" in body else True
        assert body["credits_needed"] >= 1
        assert body["daily_cap"] == 20
        pending = client.get("/api/jobs", params={"status": "pending"}).json()["total"]
        assert pending == 0

    def test_confirm入队全部不按额度截断(self, client):
        """免费目录源优先后，截断过度保守：全部入队，计量不足执行期延期（QuotaDeferred）。"""
        from app.core.config import Settings, get_settings

        client.app.dependency_overrides[get_settings] = lambda: Settings(enrich_daily_cap=1)
        try:
            product_id = self.seed_product_with_buyers(client)
            body = client.post(
                f"/api/products/{product_id}/buyers/enrich",
                json={"limit": 5, "confirm": True},
            ).json()
            assert body["enqueued"] == body["candidates"]  # 低额度也不截断入队
            assert body["enqueued"] == len(body["job_ids"])
            # credits_needed 现为「最坏情况计量数」；capped_by_quota 为信息性预计延期数
            assert body["credits_needed"] == body["enqueued"]
            assert body["capped_by_quota"] == max(
                body["enqueued"] + body["used_today"] - body["daily_cap"], 0
            )
        finally:
            client.app.dependency_overrides.pop(get_settings, None)

    def test_已有联系人的公司被跳过(self, client):
        product_id = self.seed_product_with_buyers(client)
        # 给一位种子买家加联系人 → 该公司在批量补全中被跳过
        precise = client.get(
            f"/api/products/{product_id}/buyers", params={"tier": "precise"}
        ).json()["items"][0]
        r = client.post(
            f"/api/companies/{precise['company_id']}/contacts",
            json={"name": "已有", "title": "", "email": "known@example.com"},
        )
        assert r.status_code == 201, r.text
        body = client.post(
            f"/api/products/{product_id}/buyers/enrich",
            json={"limit": 50, "confirm": False},
        ).json()
        assert body["skipped_has_contacts"] >= 1


class Test导出官网置信度:
    def test_导出联系人填官网置信度列(self, client):
        from pathlib import Path

        from app.infrastructure.orm import CompanyORM
        from app.interface.deps import get_session

        seed = Path(__file__).resolve().parents[2] / "app" / "seed"
        post_import(client,
            "/api/products/import",
            files={"file": ("p.csv", (seed / "products.csv").read_text("utf-8-sig"), "text/csv")},
        )
        post_import(client,
            "/api/bills/import",
            files={
                "file": ("b.csv", (seed / "sample_bills.csv").read_text("utf-8-sig"), "text/csv")
            },
            data={"as_of": "2026-10-09"},
        )
        session = next(client.app.dependency_overrides[get_session]())
        garment = next(
            p for p in client.get("/api/products").json() if p["code"] == "P-GARMENT"
        )
        pid = garment["product_id"]
        top = client.get(
            f"/api/products/{pid}/buyers", params={"tier": "precise"}
        ).json()["items"][0]
        company = session.get(CompanyORM, top["company_id"])
        company.website = "https://example.com"
        company.website_confidence = "high"
        session.commit()
        client.post(
            f"/api/companies/{top['company_id']}/contacts",
            json={"name": "带置信度", "title": "", "email": "conf@example.com"},
        )

        export = client.get(f"/api/products/{pid}/contacts/export.csv")
        header = export.text.splitlines()[0]
        assert "官网置信度" in header
        assert any(
            line.endswith(",https://example.com,high") or ",high" in line
            for line in export.text.splitlines()[1:]
        ), export.text[:500]
