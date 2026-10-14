"""CSV 导入后台任务：暂存 → worker 执行（含重打分）→ 结果写 jobs.result → 暂存清理。"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.infrastructure.import_jobs import enqueue_import, make_import_csv_handler
from app.infrastructure.jobs import SqlJobQueue, Worker
from app.infrastructure.orm import JobUploadORM
from tests.infra.test_queries import BILLS_CSV, PRODUCTS_CSV


def _run(session) -> None:
    handlers = {"import_csv": make_import_csv_handler(today=lambda: date(2026, 10, 9))}
    Worker(SqlJobQueue(session), handlers).run_once(datetime.now(UTC), batch=10)


class Test导入任务:
    def test_产品与提单导入结果写回且暂存清理(self, session):
        p = enqueue_import(session, "products", "p.csv", PRODUCTS_CSV)
        b = enqueue_import(session, "bills", "b.csv", BILLS_CSV, as_of=date(2026, 10, 9))
        _run(session)
        queue = SqlJobQueue(session)
        pj, bj = queue.get(p), queue.get(b)
        assert pj and pj.status == "done" and pj.result["products_upserted"] == 1
        assert bj and bj.status == "done" and bj.result["inserted_bills"] == 3
        assert bj.result["rescore"], "提单导入后应重打分"
        assert "text" not in pj.payload and pj.payload["target"] == "products"
        assert session.scalar(select(func.count()).select_from(JobUploadORM)) == 0

    def test_联系人导入(self, session):
        enqueue_import(session, "products", "p.csv", PRODUCTS_CSV)
        enqueue_import(session, "bills", "b.csv", BILLS_CSV, as_of=date(2026, 10, 9))
        c = enqueue_import(
            session,
            "contacts",
            "c.csv",
            "company_name,country,name,email\nBROOKLYN APPAREL LLC,US,Ann,ann@brooklyn.example\n",
        )
        _run(session)
        job = SqlJobQueue(session).get(c)
        assert job and job.status == "done", job
        assert job.result["added"] + len(job.result["company_not_found"]) == 1

    def test_暂存缺失永久失败不重试(self, session):
        job_id = SqlJobQueue(session).enqueue("import_csv", {"target": "bills", "upload_id": 999})
        _run(session)
        job = SqlJobQueue(session).get(job_id)
        assert job and job.status == "failed" and "重新上传" in (job.last_error or "")

    def test_未知类型永久失败(self, session):
        job_id = SqlJobQueue(session).enqueue("import_csv", {"target": "x", "upload_id": 1})
        _run(session)
        job = SqlJobQueue(session).get(job_id)
        assert job and job.status == "failed" and job.attempts == 0
