"""WP2 商机接口：加入幂等、非法转换 422、lost 必填原因、待跟进、时间线。"""

from __future__ import annotations

from pathlib import Path

from tests.import_helper import post_import

SEED_DIR = Path(__file__).resolve().parents[2] / "app" / "seed"
AS_OF = "2026-10-09"


def _seed(client) -> tuple[int, int]:
    post_import(client,
        "/api/products/import",
        files={"file": ("p.csv", (SEED_DIR / "products.csv").read_text("utf-8-sig"), "text/csv")},
    )
    post_import(client,
        "/api/bills/import",
        files={
            "file": ("b.csv", (SEED_DIR / "sample_bills.csv").read_text("utf-8-sig"), "text/csv")
        },
        data={"as_of": AS_OF},
    )
    garment = next(p for p in client.get("/api/products").json() if p["code"] == "P-GARMENT")
    top = client.get(
        f"/api/products/{garment['product_id']}/buyers", params={"tier": "precise"}
    ).json()["items"][0]
    return garment["product_id"], top["company_id"]


class Test加入与列表:
    def test_加入跟进幂等(self, client):
        pid, cid = _seed(client)
        first = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid})
        assert first.status_code == 201, first.text
        second = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid})
        assert second.status_code == 201  # 幂等返回既有
        assert second.json()["opportunity_id"] == first.json()["opportunity_id"]
        assert client.get("/api/opportunities").json().__len__() == 1

    def test_按产品与阶段过滤(self, client):
        pid, cid = _seed(client)
        opp = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid}).json()
        client.patch(f"/api/opportunities/{opp['opportunity_id']}", json={"stage": "replied"})
        assert len(client.get("/api/opportunities", params={"stage": "replied"}).json()) == 1
        assert len(client.get("/api/opportunities", params={"stage": "lead"}).json()) == 0


class Test阶段变更:
    def test_倒退返回422(self, client):
        pid, cid = _seed(client)
        opp = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid}).json()
        client.patch(f"/api/opportunities/{opp['opportunity_id']}", json={"stage": "replied"})
        r = client.patch(
            f"/api/opportunities/{opp['opportunity_id']}", json={"stage": "contacted"}
        )
        assert r.status_code == 422
        assert "不允许" in r.json()["detail"]

    def test_lost缺原因422带原因成功并可重开(self, client):
        pid, cid = _seed(client)
        opp = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid}).json()
        oid = opp["opportunity_id"]
        assert client.patch(f"/api/opportunities/{oid}", json={"stage": "lost"}).status_code == 422
        lost = client.patch(
            f"/api/opportunities/{oid}", json={"stage": "lost", "closed_reason": "无回复"}
        ).json()
        assert lost["closed_reason"] == "无回复"
        reopened = client.patch(f"/api/opportunities/{oid}", json={"stage": "lead"}).json()
        assert reopened["stage"] == "lead"

    def test_阶段变更产生stage_change活动(self, client):
        pid, cid = _seed(client)
        opp = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid}).json()
        client.patch(f"/api/opportunities/{opp['opportunity_id']}", json={"stage": "contacted"})
        timeline = client.get(f"/api/opportunities/{opp['opportunity_id']}/timeline").json()
        assert timeline[0]["kind"] == "stage_change"


class Test活动与时间线:
    def test_写活动回写意愿(self, client):
        pid, cid = _seed(client)
        opp = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid}).json()
        oid = opp["opportunity_id"]
        r = client.post(
            f"/api/opportunities/{oid}/activities",
            json={"kind": "call", "summary": "通了电话", "intent_after": "hot"},
        )
        assert r.status_code == 201, r.text
        refreshed = client.get("/api/opportunities").json()[0]
        assert refreshed["intent"] == "hot"

    def test_非法活动类型422与404(self, client):
        pid, cid = _seed(client)
        opp = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid}).json()
        oid = opp["opportunity_id"]
        bad = client.post(
            f"/api/opportunities/{oid}/activities", json={"kind": "smoke", "summary": "x"}
        )
        assert bad.status_code == 422
        assert client.get("/api/opportunities/99999/timeline").status_code == 404


class Test今日待跟进:
    def test_due_today过滤(self, client):
        from datetime import date, timedelta

        pid, cid = _seed(client)
        opp = client.post("/api/opportunities", json={"product_id": pid, "company_id": cid}).json()
        assert client.get("/api/opportunities", params={"due": "today"}).json() == []
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        client.patch(
            f"/api/opportunities/{opp['opportunity_id']}",
            json={"next_follow_up_on": yesterday},
        )
        due = client.get("/api/opportunities", params={"due": "today"}).json()
        assert len(due) == 1 and due[0]["stage"] == "lead"
