"""接口层：任务状态只读端点。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.infrastructure.jobs import SqlJobQueue

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)


def seed_jobs(client) -> None:
    # 经由被 override 的 get_session 拿同一会话，直接走队列入队
    from app.interface.deps import get_session

    session = next(client.app.dependency_overrides[get_session]())
    queue = SqlJobQueue(session)
    queue.enqueue("find_contacts", {"company_id": 1}, run_after=NOW)
    queue.enqueue("crawl_website", {"company_id": 2}, run_after=NOW)
    queue.claim(NOW)  # 认领最早一条 → running


class Test任务状态:
    def test_只读列表返回全部状态(self, client):
        seed_jobs(client)
        r = client.get("/api/jobs")
        assert r.status_code == 200
        body = r.json()
        statuses = {j["status"] for j in body["items"]}
        assert statuses == {"running", "pending"}
        assert body["total"] == 2

    def test_状态过滤(self, client):
        seed_jobs(client)
        body = client.get("/api/jobs", params={"status": "pending"}).json()
        assert body["total"] == 1
        assert body["items"][0]["kind"] == "crawl_website"

    def test_非法状态返回422(self, client):
        assert client.get("/api/jobs", params={"status": "zombie"}).status_code == 422

    def test_任务字段形状(self, client):
        seed_jobs(client)
        item = client.get("/api/jobs").json()["items"][0]
        assert {
            "id", "kind", "status", "payload", "attempts",
            "max_attempts", "run_after", "last_error", "created_at",
        } <= set(item.keys())
