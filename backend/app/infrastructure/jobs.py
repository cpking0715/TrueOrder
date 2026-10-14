"""基于 PostgreSQL 的任务队列与 worker（实现 domain.jobs 的规则与端口）。

认领互斥靠 SELECT ... FOR UPDATE SKIP LOCKED：多 worker 并发拉取不重复；
每个队列方法自带 commit，队列调用之间事务边界清晰。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.logging import get_logger, job_id_var
from app.domain.jobs import (
    DEAD_TASK_TIMEOUT,
    Job,
    next_run_after,
    should_retry,
)
from app.infrastructure.orm import JobORM

# 处理器可返回结果摘要 dict（写入 jobs.result），无结果返回 None
Handler = Callable[[Session, dict[str, Any]], dict[str, Any] | None]

log = get_logger("app.worker")


def _to_job(row: JobORM) -> Job:
    return Job(
        id=row.id,
        kind=row.kind,
        payload=row.payload or {},
        status=row.status,  # type: ignore[arg-type]
        run_after=row.run_after,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        last_error=row.last_error,
        locked_at=row.locked_at,
        created_at=row.created_at,
        result=row.result,
    )


class SqlJobQueue:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        run_after: datetime | None = None,
        max_attempts: int = 3,
    ) -> int:
        row = JobORM(kind=kind, payload=payload or {}, max_attempts=max_attempts)
        if run_after is not None:
            row.run_after = run_after
        self._session.add(row)
        self._session.flush()
        self._session.commit()
        return row.id

    @property
    def session(self) -> Session:
        """处理器与 worker 共用的会话（只读暴露，事务由队列方法管理）。"""
        return self._session

    def claim(self, now: datetime, limit: int = 1) -> list[Job]:
        rows = (
            self._session.execute(
                select(JobORM)
                .where(JobORM.status == "pending", JobORM.run_after <= now)
                .order_by(JobORM.run_after, JobORM.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.status = "running"
            row.locked_at = now
        self._session.commit()
        return [_to_job(r) for r in rows]

    def complete(self, job_id: int, result: dict[str, Any] | None = None) -> None:
        self._session.execute(
            update(JobORM)
            .where(JobORM.id == job_id)
            .values(status="done", last_error=None, result=result)
        )
        self._session.commit()

    def fail(self, job_id: int, error: str, now: datetime) -> None:
        """失败：未达上限回 pending 并按退避重跑；达到上限置 failed。"""
        row = self._session.get(JobORM, job_id)
        if row is None:
            return
        row.attempts += 1
        row.last_error = error[:2000]
        if should_retry(row.attempts, row.max_attempts):
            row.status = "pending"
            row.run_after = next_run_after(row.attempts, now)
            row.locked_at = None
        else:
            row.status = "failed"
            row.locked_at = None
        self._session.commit()

    def defer(self, job_id: int, run_after: datetime) -> None:
        """延期重跑：回 pending、attempts 不增（不是失败）。"""
        row = self._session.get(JobORM, job_id)
        if row is None:
            return
        row.status = "pending"
        row.run_after = run_after
        row.locked_at = None
        row.last_error = f"延期至 {run_after:%Y-%m-%d %H:%M}（额度用尽）"
        self._session.commit()

    def fail_permanent(self, job_id: int, error: str) -> None:
        row = self._session.get(JobORM, job_id)
        if row is None:
            return
        row.status = "failed"
        row.last_error = error[:2000]
        row.locked_at = None
        self._session.commit()

    def recover_dead(self, now: datetime) -> int:
        """running 超过僵死阈值的任务回收：有余量回 pending，否则 failed。

        阈值在 SQL 里过滤（只取 locked_at 早于 now - DEAD_TASK_TIMEOUT 的行并加锁跳过），
        不再把全部 running 行拉回 Python 判断。
        """
        rows = list(
            self._session.scalars(
                select(JobORM)
                .where(
                    JobORM.status == "running",
                    JobORM.locked_at.is_not(None),
                    JobORM.locked_at < now - DEAD_TASK_TIMEOUT,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.attempts += 1
            row.locked_at = None
            if should_retry(row.attempts, row.max_attempts):
                row.status = "pending"
                row.run_after = now
            else:
                row.status = "failed"
                row.last_error = (row.last_error or "") + "; recovered as dead"
            log.warning(
                "recovered dead job",
                extra={"job_id": row.id, "kind": row.kind, "new_status": row.status},
            )
        self._session.commit()
        return len(rows)

    def get(self, job_id: int) -> Job | None:
        row = self._session.get(JobORM, job_id)
        return _to_job(row) if row else None

    def list_jobs(self, status: str | None = None, limit: int = 100) -> list[Job]:
        stmt = select(JobORM).order_by(JobORM.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(JobORM.status == status)
        return [_to_job(r) for r in self._session.scalars(stmt)]


class PermanentJobError(Exception):
    """确定性失败（业务规则判定重试无意义）：处理器抛出即永久失败，不退避。"""


class QuotaDeferred(Exception):
    """额度用尽等日滚动资源受限：任务延期到 run_after，不算失败、不进退避。"""

    def __init__(self, run_after: datetime, reason: str = "") -> None:
        super().__init__(reason or f"额度用尽，延期至 {run_after:%Y-%m-%d %H:%M}")
        self.run_after = run_after


class Worker:
    """单轮/循环执行器：先回收僵死，再认领到期任务并分发给处理器。"""

    def __init__(self, queue: SqlJobQueue, handlers: dict[str, Handler]) -> None:
        self._queue = queue
        self._handlers = handlers

    def run_once(self, now: datetime, batch: int = 10, should_stop=None) -> int:
        """一次最多处理 batch 个任务，但**每次只认领 1 个**：

        旧实现一次认领 batch 个再串行执行，排在后面的任务早早被标 running，
        前面任务慢（爬虫同主机限速）时可能超过僵死阈值被回收后重复执行。
        should_stop：可选回调，返回 True 时在两个任务之间停下（SIGTERM 优雅退出）。
        """
        self._queue.recover_dead(now)
        handled = 0
        for _ in range(batch):
            if should_stop is not None and should_stop():
                break
            jobs = self._queue.claim(now, limit=1)
            if not jobs:
                break
            if self._run_job(jobs[0], now):
                handled += 1
        return handled

    def _run_job(self, job: Job, now: datetime) -> bool:
        token = job_id_var.set(job.id)
        try:
            handler = self._handlers.get(job.kind)
            if handler is None:
                log.error("unknown job kind", extra={"kind": job.kind})
                self._queue.fail_permanent(job.id, f"unknown job kind: {job.kind}")
                return False
            try:
                result = handler(self._queue.session, job.payload)
                self._queue.complete(job.id, result if isinstance(result, dict) else None)
                log.info("job done", extra={"kind": job.kind})
                return True
            except QuotaDeferred as exc:
                self._queue.session.rollback()
                self._queue.defer(job.id, exc.run_after)
                log.info("job deferred", extra={"kind": job.kind, "run_after": exc.run_after})
            except PermanentJobError as exc:
                self._queue.session.rollback()
                self._queue.fail_permanent(job.id, str(exc))
                log.warning("job failed permanently", extra={"kind": job.kind, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - 队列必须吞掉一切处理器异常
                self._queue.session.rollback()
                self._queue.fail(job.id, f"{type(exc).__name__}: {exc}", now)
                log.warning("job failed, will retry if attempts remain",
                            extra={"kind": job.kind}, exc_info=True)
            return False
        finally:
            job_id_var.reset(token)
