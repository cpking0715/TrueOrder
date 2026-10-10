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

from app.domain.jobs import (
    Job,
    is_dead,
    next_run_after,
    should_retry,
)
from app.infrastructure.orm import JobORM

Handler = Callable[[Session, dict[str, Any]], None]


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

    def complete(self, job_id: int) -> None:
        self._session.execute(
            update(JobORM).where(JobORM.id == job_id).values(status="done", last_error=None)
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

    def fail_permanent(self, job_id: int, error: str) -> None:
        row = self._session.get(JobORM, job_id)
        if row is None:
            return
        row.status = "failed"
        row.last_error = error[:2000]
        row.locked_at = None
        self._session.commit()

    def recover_dead(self, now: datetime) -> int:
        """running 超过僵死阈值的任务回收：有余量回 pending，否则 failed。"""
        rows = list(self._session.scalars(select(JobORM).where(JobORM.status == "running")))
        recovered = 0
        for row in rows:
            if not is_dead(row.locked_at, now):
                continue
            row.attempts += 1
            row.locked_at = None
            if should_retry(row.attempts, row.max_attempts):
                row.status = "pending"
                row.run_after = now
            else:
                row.status = "failed"
                row.last_error = (row.last_error or "") + "; recovered as dead"
            recovered += 1
        self._session.commit()
        return recovered

    def list_jobs(self, status: str | None = None, limit: int = 100) -> list[Job]:
        stmt = select(JobORM).order_by(JobORM.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(JobORM.status == status)
        return [_to_job(r) for r in self._session.scalars(stmt)]


class Worker:
    """单轮/循环执行器：先回收僵死，再认领到期任务并分发给处理器。"""

    def __init__(self, queue: SqlJobQueue, handlers: dict[str, Handler]) -> None:
        self._queue = queue
        self._handlers = handlers

    def run_once(self, now: datetime, batch: int = 10) -> int:
        self._queue.recover_dead(now)
        jobs = self._queue.claim(now, limit=batch)
        handled = 0
        for job in jobs:
            handler = self._handlers.get(job.kind)
            if handler is None:
                self._queue.fail_permanent(job.id, f"unknown job kind: {job.kind}")
                continue
            try:
                handler(self._queue.session, job.payload)
                self._queue.complete(job.id)
                handled += 1
            except Exception as exc:  # noqa: BLE001 - 队列必须吞掉一切处理器异常
                self._queue.session.rollback()
                self._queue.fail(job.id, f"{type(exc).__name__}: {exc}", now)
        return handled
