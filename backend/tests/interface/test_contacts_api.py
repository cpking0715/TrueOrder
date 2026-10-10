"""联系人接口层：CRUD、409/422、CSV 导入、官网字段、按筛选导出。"""

from __future__ import annotations

from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[2] / "app" / "seed"
AS_OF = "2026-10-09"


def _seed(client) -> dict:
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
    precise = client.get("/api/products/1/buyers", params={"tier": "precise"}).json()
    assert precise["total"] >= 1
    return {"company_id": precise["items"][0]["company_id"], "product_id": 1}


class Test联系人CRUD:
    def test_新增联系人字段规范化与通用邮箱标签(self, client):
        ids = _seed(client)
        r = client.post(
            f"/api/companies/{ids['company_id']}/contacts",
            json={"name": "John Smith", "title": " Purchasing Manager ",
                  "email": "  JOHN@Example.COM ", "phone": "+1-555-0100"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == "john@example.com"
        assert body["title"] == "Purchasing Manager"
        assert body["is_generic"] is False
        assert body["source"] == "manual"

    def test_通用邮箱自动打标签(self, client):
        ids = _seed(client)
        r = client.post(
            f"/api/companies/{ids['company_id']}/contacts",
            json={"email": "SALES@example.com"},
        )
        assert r.status_code == 201
        assert r.json()["is_generic"] is True
        assert r.json()["name"] is None

    def test_同公司同邮箱大小写不同返回409(self, client):
        ids = _seed(client)
        first = client.post(
            f"/api/companies/{ids['company_id']}/contacts", json={"email": "a@b.com"}
        )
        assert first.status_code == 201
        again = client.post(
            f"/api/companies/{ids['company_id']}/contacts", json={"email": "A@B.COM"}
        )
        assert again.status_code == 409

    def test_坏邮箱格式返回422(self, client):
        ids = _seed(client)
        r = client.post(
            f"/api/companies/{ids['company_id']}/contacts", json={"email": "not-an-email"}
        )
        assert r.status_code == 422

    def test_公司不存在404(self, client):
        assert client.get("/api/companies/99999/contacts").status_code == 404
        r = client.post("/api/companies/99999/contacts", json={"email": "a@b.com"})
        assert r.status_code == 404

    def test_更新与标记不再联系(self, client):
        ids = _seed(client)
        contact_id = client.post(
            f"/api/companies/{ids['company_id']}/contacts",
            json={"name": "A", "email": "a@b.com"},
        ).json()["contact_id"]
        r = client.patch(f"/api/contacts/{contact_id}", json={"do_not_contact": True,
                                                              "title": "GM"})
        assert r.status_code == 200
        body = r.json()
        assert body["do_not_contact"] is True and body["title"] == "GM"
        # 更新撞他人邮箱 → 409
        client.post(f"/api/companies/{ids['company_id']}/contacts",
                    json={"email": "c@d.com"})
        clash = client.patch(f"/api/contacts/{contact_id}", json={"email": "C@D.com"})
        assert clash.status_code == 409

    def test_删除联系人后查不到(self, client):
        ids = _seed(client)
        contact_id = client.post(
            f"/api/companies/{ids['company_id']}/contacts", json={"email": "a@b.com"}
        ).json()["contact_id"]
        assert client.delete(f"/api/contacts/{contact_id}").status_code == 204
        assert client.get(f"/api/companies/{ids['company_id']}/contacts").json() == []
        assert client.delete(f"/api/contacts/{contact_id}").status_code == 404

    def test_官网字段更新(self, client):
        ids = _seed(client)
        r = client.patch(
            f"/api/companies/{ids['company_id']}",
            json={"website": "https://example.com", "website_confirmed": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["website"] == "https://example.com"
        assert body["website_confirmed"] is True
        assert client.patch("/api/companies/99999", json={"website": "x"}).status_code == 404


class Test联系人CSV导入:
    def _csv(self, rows: list[list[str]]) -> str:
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["company_id", "company_name", "country", "name", "title",
                         "email", "phone"])
        for row in rows:
            writer.writerow(row)
        return buf.getvalue()

    def test_按id与按名称国家两种定位(self, client):
        ids = _seed(client)
        csv_text = self._csv(
            [
                [str(ids["company_id"]), "", "", "John", "PM", "john@ex.com", ""],
                ["", "BROOKLYN APPAREL", "US", "Mary", "GM", "mary@ex.com", ""],
            ]
        )
        r = client.post(
            "/api/contacts/import", files={"file": ("c.csv", csv_text, "text/csv")}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["added"] == 2 and body["duplicates"] == 0

    def test_重复与未找到企业(self, client):
        ids = _seed(client)
        csv_text = self._csv(
            [
                [str(ids["company_id"]), "", "", "J", "", "dup@ex.com", ""],
                [str(ids["company_id"]), "", "", "J2", "", "DUP@ex.com", ""],
                ["99999", "", "", "X", "", "x@ex.com", ""],
            ]
        )
        body = client.post(
            "/api/contacts/import", files={"file": ("c.csv", csv_text, "text/csv")}
        ).json()
        assert body["added"] == 1
        assert body["duplicates"] == 1
        assert len(body["company_not_found"]) == 1


class Test联系人导出:
    def _setup_contacts(self, client):
        ids = _seed(client)
        cid = ids["company_id"]
        client.post(f"/api/companies/{cid}/contacts",
                    json={"name": "Keep", "email": "keep@ex.com"})
        client.post(f"/api/companies/{cid}/contacts",
                    json={"name": "DNC", "email": "dnc@ex.com"})
        client.post(f"/api/companies/{cid}/contacts",
                    json={"name": "Bad", "email": "bad@ex.com"})
        dnc_id = None
        bad_id = None
        for c in client.get(f"/api/companies/{cid}/contacts").json():
            if c["email"] == "dnc@ex.com":
                dnc_id = c["contact_id"]
            if c["email"] == "bad@ex.com":
                bad_id = c["contact_id"]
        client.patch(f"/api/contacts/{dnc_id}", json={"do_not_contact": True})
        return ids, cid, bad_id

    def test_默认排除不再联系与无效验证状态(self, client):
        ids, cid, bad_id = self._setup_contacts(client)
        # 默认排除断言：dnc 被排除，keep 在（invalid 场景由 include_invalid 用例覆盖）
        export = client.get(
            f"/api/products/{ids['product_id']}/contacts/export.csv",
            params={"tier": "precise"},
        )
        assert export.status_code == 200
        text = export.text
        assert "keep@ex.com" in text
        assert "dnc@ex.com" not in text
        header = text.splitlines()[0].lstrip("\ufeff")
        assert "联系人姓名" in header and "官网" in header and "官网置信度" in header
        # 每联系人一行：该精准公司默认只有 keep 一行
        assert "keep@ex.com" in text and text.count("keep@ex.com") == 1

    def test_include_invalid放开无效联系人(self, client):
        ids, cid, _ = self._setup_contacts(client)
        export_all = client.get(
            f"/api/products/{ids['product_id']}/contacts/export.csv",
            params={"tier": "precise", "include_invalid": "true"},
        ).text
        # include_invalid 只放开验证状态，不放开 do_not_contact
        assert "dnc@ex.com" not in export_all
        assert "bad@ex.com" in export_all
        assert "keep@ex.com" in export_all


class Test生产会话语义:
    def test_联系人写入跨请求持久化(self, engine, monkeypatch):
        """模拟生产 get_session（每请求独立会话）：写请求的数据必须在后续请求可见。

        复现 blocker：repo 只 flush 不 commit 时，会话关闭即回滚，生产环境丢失全部写入。
        """
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.infrastructure.orm import Base
        from app.interface import deps
        from app.interface.main import create_app

        engine_fresh = create_engine(engine.url.render_as_string(hide_password=False))
        Base.metadata.drop_all(engine_fresh)
        Base.metadata.create_all(engine_fresh)
        monkeypatch.setattr(deps, "_session_factory", lambda: sessionmaker(bind=engine_fresh))
        app = create_app()  # 不 override get_session：走真实的 deps.get_session
        with TestClient(app) as client:
            _seed(client)
            ids = {
                "company_id": None,
                "product_id": 1,
            }
            precise = client.get("/api/products/1/buyers", params={"tier": "precise"}).json()
            ids["company_id"] = precise["items"][0]["company_id"]
            created = client.post(
                f"/api/companies/{ids['company_id']}/contacts",
                json={"name": "Persist", "email": "persist@ex.com"},
            )
            assert created.status_code == 201, created.text
            listing = client.get(f"/api/companies/{ids['company_id']}/contacts")
            emails = [c["email"] for c in listing.json()]
            assert "persist@ex.com" in emails, f"写请求的数据丢失: {emails}"
        engine_fresh.dispose()


class Test导入与更新的脏写行为:
    def test_导入中途重复不吞掉前面行(self, client):
        ids = _seed(client)
        cid = ids["company_id"]
        pre = client.post(f"/api/companies/{cid}/contacts", json={"email": "dup@ex.com"})
        assert pre.status_code == 201, pre.text
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["company_id", "company_name", "country", "name", "title", "email", "phone"]
        )
        writer.writerow([cid, "", "", "F", "", "first@ex.com", ""])
        writer.writerow([cid, "", "", "D", "", "dup@ex.com", ""])
        writer.writerow([cid, "", "", "S", "", "second@ex.com", ""])
        csv_text = buf.getvalue()
        body = client.post(
            "/api/contacts/import", files={"file": ("c.csv", csv_text, "text/csv")}
        ).json()
        assert body["added"] == 2 and body["duplicates"] == 1
        emails = {c["email"] for c in client.get(f"/api/companies/{cid}/contacts").json()}
        assert {"first@ex.com", "second@ex.com"} <= emails, "中途重复回滚吞掉了前面行"

    def test_坏邮箱422不改动其他字段(self, client):
        ids = _seed(client)
        contact_id = client.post(
            f"/api/companies/{ids['company_id']}/contacts",
            json={"name": "A", "title": "PM", "email": "a@b.com"},
        ).json()["contact_id"]
        r = client.patch(
            f"/api/contacts/{contact_id}", json={"title": "GM", "email": "bad-email"}
        )
        assert r.status_code == 422
        body = client.get(f"/api/companies/{ids['company_id']}/contacts").json()[0]
        assert body["title"] == "PM", "422 前其他字段已被脏改"

    def test_按名称定位缺国家归入无效行(self, client):
        _seed(client)
        csv_text = (
            "company_id,company_name,country,name,title,email,phone\n"
            ",BROOKLYN APPAREL,,NoCountry,,nc@ex.com,\n"
        )
        body = client.post(
            "/api/contacts/import", files={"file": ("c.csv", csv_text, "text/csv")}
        ).json()
        assert body["added"] == 0
        assert len(body["invalid_rows"]) == 1 and "国家" in body["invalid_rows"][0]


class Test失败路径不提交:
    def test_409路径不落库_生产式会话(self, engine, monkeypatch):
        """回归锁：失败请求不得因会话 teardown 而意外提交（响应后提交竞态的镜像用例）。"""
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from app.infrastructure.orm import Base
        from app.interface import deps
        from app.interface.main import create_app

        engine_fresh = create_engine(engine.url.render_as_string(hide_password=False))
        Base.metadata.drop_all(engine_fresh)
        Base.metadata.create_all(engine_fresh)
        monkeypatch.setattr(deps, "_session_factory", lambda: sessionmaker(bind=engine_fresh))
        app = create_app()
        with TestClient(app) as client:
            _seed(client)
            precise = client.get("/api/products/1/buyers", params={"tier": "precise"}).json()
            cid = precise["items"][0]["company_id"]
            first = client.post(
                f"/api/companies/{cid}/contacts", json={"email": "race@ex.com"}
            )
            assert first.status_code == 201
            clash = client.post(
                f"/api/companies/{cid}/contacts", json={"email": "RACE@ex.com"}
            )
            assert clash.status_code == 409
            with engine_fresh.connect() as conn:
                count = conn.execute(
                    text("select count(*) from contacts where email = 'race@ex.com'")
                ).scalar_one()
        engine_fresh.dispose()
        assert count == 1, "409 路径不应产生第二条或丢失第一条"
