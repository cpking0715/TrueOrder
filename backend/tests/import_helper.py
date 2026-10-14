"""CSV 导入已改后台任务：测试里 POST 后同步跑 import_csv 任务，返回带结果的伪响应。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class ImportResult:
    status_code: int
    body: Any
    job_id: int | None = None

    def json(self) -> Any:
        return self.body

    @property
    def text(self) -> str:
        return str(self.body)


def drain_import_jobs(client) -> None:
    from app.infrastructure.import_jobs import make_import_csv_handler
    from app.infrastructure.jobs import SqlJobQueue, Worker
    from app.interface.deps import get_session

    # 有 override 用测试会话；否则（生产式会话用例）走真实 get_session
    gen = client.app.dependency_overrides.get(get_session, get_session)()
    session = next(gen)
    Worker(SqlJobQueue(session), {"import_csv": make_import_csv_handler()}).run_once(
        datetime.now(UTC), batch=50
    )
    gen.close()


def post_import(client, url: str, **kwargs: Any):
    """POST 导入：非 202（如 413/422 上传校验失败）原样返回；202 则跑完任务返回 result。"""
    r = client.post(url, **kwargs)
    if r.status_code != 202:
        return r
    job_id = r.json()["job_id"]
    drain_import_jobs(client)
    job = client.get(f"/api/jobs/{job_id}").json()
    if job["status"] != "done":
        return ImportResult(500, job, job_id)
    return ImportResult(200, job["result"], job_id)
