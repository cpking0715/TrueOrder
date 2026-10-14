"""任务状态只读路由：worker 在另一个进程跑，界面只看队列。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.infrastructure.jobs import SqlJobQueue
from app.interface.deps import get_session
from app.interface.schemas import JobOut, JobsListOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=JobsListOut)
def list_jobs(
    status: str | None = Query(default=None, pattern="^(pending|running|done|failed)$"),
    limit: int = Query(default=100, ge=1, le=200),
    session: Session = Depends(get_session),
):
    queue = SqlJobQueue(session)
    jobs = queue.list_jobs(status=status, limit=limit)
    return JobsListOut(
        items=[JobOut(**job.__dict__) for job in jobs],
        total=len(jobs),
    )


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, session: Session = Depends(get_session)):
    job = SqlJobQueue(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JobOut(**job.__dict__)
