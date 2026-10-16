"""出海包接口（TestClient + overrides）：验收主链路与各页端点的护栏/校验。

验收链路：录入 3 个产品 → 导入 50 个买家 → 生成 1 封开发信 → 登记 1 个询盘并导出 PI。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.kit_sales import DraftContext, DraftText
from app.domain.outreach import UNSUBSCRIBE_LINE
from app.interface.routers.kit_sales import get_draft_writer

FIXTURE = Path(__file__).parent.parent / "fixtures" / "kit_kidswear_buyers.csv"
KIDSWEAR = [
    ("Organic Baby Romper", "610322"),
    ("Girls Cotton Dress", "620442"),
    ("Boys Denim Shorts", "620342"),
]


class FakeWriter:
    def write(self, ctx: DraftContext) -> DraftText:
        return DraftText(f"[fake] {ctx.product}", f"Dear {ctx.company}, MOQ {ctx.moq}.")


def _make_products(client) -> list[int]:
    ids = []
    for name, hs in KIDSWEAR:
        r = client.post(
            "/api/products", json={"name": name, "hs_code": hs, "buyer_type": "importer"}
        )
        assert r.status_code == 201, r.text
        pid = r.json()["product_id"]
        prof = client.put(
            f"/api/kit/products/{pid}/profile",
            json={
                "image_url": "https://img.example.com/x.jpg", "specs": "100% cotton",
                "moq": 300, "lead_time_days": 30, "selling_points": ["OEKO-TEX"],
            },
        )
        assert prof.status_code == 200, prof.text
        ids.append(pid)
    return ids


def _import(client):
    with FIXTURE.open("rb") as f:
        return client.post(
            "/api/kit/buyers/import", files={"file": ("buyers.csv", f, "text/csv")}
        )


def test_验收主链路_3产品_50买家_1封开发信_1询盘PI(client):
    pids = _make_products(client)
    assert sum(p["featured"] for p in client.get("/api/kit/products").json()) == 3

    imp = _import(client).json()
    assert imp["buyers_tagged"] == 50 and imp["duplicates_in_file"] == 2
    buyers = client.get("/api/kit/buyers").json()
    assert len(buyers) == 50
    buyer = buyers[0]

    client.app.dependency_overrides[get_draft_writer] = lambda: FakeWriter()
    d = client.post(
        "/api/kit/drafts",
        json={"product_id": pids[0], "company_id": buyer["company_id"],
              "contact_id": buyer["contact_id"], "channel": "email"},
    )
    assert d.status_code == 201, d.text
    draft = d.json()
    assert draft["source"] == "llm" and draft["sent"] is False
    assert draft["subject"] == "[fake] Organic Baby Romper"
    assert draft["body"].endswith(UNSUBSCRIBE_LINE)
    assert len(draft["follow_up_on"]) == 2 and draft["next_follow_up"] == draft["follow_up_on"][0]
    txt = client.get(f"/api/kit/drafts/{draft['id']}/export.txt")
    assert txt.text.startswith("Subject: [fake] Organic Baby Romper")

    inq = client.post(
        "/api/kit/inquiries",
        json={"company_id": buyer["company_id"], "product_id": pids[0], "quantity": 600,
              "unit_price": "3.25", "currency": "usd"},
    )
    assert inq.status_code == 201, inq.text
    assert inq.json()["total"] == "1950.00" and inq.json()["status_label"] == "新询盘"
    iid = inq.json()["id"]
    assert client.patch(f"/api/kit/inquiries/{iid}", json={"status": "quoted"}).status_code == 200
    pdf = client.get(f"/api/kit/inquiries/{iid}/pi.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and b"USD 1950.00" in pdf.content
    assert "PI-" in pdf.headers["content-disposition"]


def test_任务台_勾选持久化_今天前移_未知任务404(client):
    assert client.get("/api/kit/tasks").json()["today"] == 1
    assert client.put("/api/kit/tasks/d1_buyer_type", json={"done": True}).status_code == 204
    body = client.get("/api/kit/tasks").json()
    assert body["today"] == 2 and body["done_count"] == 1 and body["total"] == 15
    assert client.put("/api/kit/tasks/nope", json={"done": True}).status_code == 404


def test_产品档案_404_422_主推上限409(client):
    assert client.put("/api/kit/products/999/profile", json={}).status_code == 404
    pids = _make_products(client)
    bad = client.put(f"/api/kit/products/{pids[0]}/profile", json={"moq": 0})
    assert bad.status_code == 422 and "MOQ" in bad.json()["detail"]
    for i in range(2):
        r = client.post(
            "/api/products", json={"name": f"Extra {i}", "hs_code": "611120", "buyer_type": "importer"}
        )
        client.put(f"/api/kit/products/{r.json()['product_id']}/profile", json={"moq": 1})
    r = client.post("/api/products", json={"name": "Sixth", "hs_code": "611120", "buyer_type": "importer"})
    six = client.put(f"/api/kit/products/{r.json()['product_id']}/profile", json={"moq": 1})
    assert six.status_code == 409
    # 已主推的再保存不受上限影响；非主推可存
    assert client.put(f"/api/kit/products/{pids[0]}/profile", json={"moq": 2}).status_code == 200
    off = {"moq": 1, "featured": False}
    assert client.put(f"/api/kit/products/{r.json()['product_id']}/profile", json=off).status_code == 200


def test_买家标签_筛选与非法取值(client):
    _import(client)
    b = client.get("/api/kit/buyers", params={"country": "ae"}).json()
    assert len(b) == 10
    cid = b[0]["company_id"]
    assert client.patch(f"/api/kit/buyers/{cid}", json={"stage": "bogus"}).status_code == 422
    assert client.patch(f"/api/kit/buyers/{cid}", json={"stage": "contacted"}).status_code == 204
    assert len(client.get("/api/kit/buyers", params={"stage": "contacted"}).json()) == 1
    assert client.patch("/api/kit/buyers/999999", json={"stage": "new"}).status_code == 404


@pytest.fixture()
def ready(client):
    pids = _make_products(client)
    _import(client)
    return pids, client.get("/api/kit/buyers").json()


def test_无AI_Key走模板_WhatsApp无主题(client, ready):
    pids, buyers = ready
    client.app.dependency_overrides[get_draft_writer] = lambda: None
    r = client.post(
        "/api/kit/drafts",
        json={"product_id": pids[1], "company_id": buyers[2]["company_id"], "channel": "whatsapp"},
    )
    assert r.status_code == 201 and r.json()["source"] == "template"
    assert r.json()["subject"] == "" and "MOQ 300" in r.json()["body"]


def test_草稿护栏_抑制名单与勿联系409_无档案422(client, ready):
    pids, buyers = ready
    client.app.dependency_overrides[get_draft_writer] = lambda: None
    target = buyers[0]
    domain = target["email"].split("@")[1]
    client.post("/api/outreach/suppressions", json={"domain": domain, "reason": "manual"})
    body = {"product_id": pids[0], "company_id": target["company_id"],
            "contact_id": target["contact_id"]}
    assert client.post("/api/kit/drafts", json=body).status_code == 409
    other = buyers[1]
    client.patch(f"/api/contacts/{other['contact_id']}", json={"do_not_contact": True})
    body2 = {**body, "company_id": other["company_id"], "contact_id": other["contact_id"]}
    assert client.post("/api/kit/drafts", json=body2).status_code == 409
    # 联系人不属于该买家 → 404
    body3 = {**body2, "contact_id": target["contact_id"]}
    assert client.post("/api/kit/drafts", json=body3).status_code == 404
    r = client.post("/api/products", json={"name": "NoProfile", "hs_code": "611120", "buyer_type": "importer"})
    body4 = {"product_id": r.json()["product_id"], "company_id": buyers[3]["company_id"]}
    assert client.post("/api/kit/drafts", json=body4).status_code == 422


def test_询盘_非法转换422_校验422_不存在404(client, ready):
    pids, buyers = ready
    base = {"company_id": buyers[0]["company_id"], "product_id": pids[0]}
    assert client.post("/api/kit/inquiries", json={**base, "quantity": 0, "unit_price": "1"}).status_code == 422
    missing = {**base, "company_id": 999999, "quantity": 1, "unit_price": "1"}
    assert client.post("/api/kit/inquiries", json=missing).status_code == 404
    iid = client.post("/api/kit/inquiries", json={**base, "quantity": 1, "unit_price": "1"}).json()["id"]
    r = client.patch(f"/api/kit/inquiries/{iid}", json={"status": "won"})
    assert r.status_code == 422 and "新询盘" in r.json()["detail"]
    assert client.get("/api/kit/inquiries/999999/pi.pdf").status_code == 404
    assert len(client.get("/api/kit/inquiries").json()) == 1
