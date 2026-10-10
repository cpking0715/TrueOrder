"""后台任务的领域规则：退避、僵死判定、重试边界（纯函数）。

任务队列的存取属于基础设施；这里只回答「失败后何时再跑、
多久算僵死、还该不该重试」这三类纯业务问题。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

JobStatus = Literal["pending", "running", "done", "failed"]
# 任务种类：第一期实际产生 find_contacts / crawl_website / verify_email（配 Hunter Key 时）；
# send_email / poll_imap 为第二期预留（见 DEV-SPEC 3.2）。
JobKind = Literal["send_email", "find_contacts", "crawl_website", "poll_imap", "verify_email"]

DEAD_TASK_TIMEOUT = timedelta(minutes=10)
BACKOFF_BASE = timedelta(seconds=60)
BACKOFF_CAP = timedelta(hours=1)


@dataclass(frozen=True)
class Job:
    """一条后台任务（基础设施层读出后转成此领域对象）。"""

    id: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = "pending"
    run_after: datetime | None = None
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    locked_at: datetime | None = None
    created_at: datetime | None = None


def next_run_after(attempts: int, now: datetime) -> datetime:
    """第 n 次失败后的重跑时间：60s * 2^(n-1)，封顶 1 小时。"""
    n = max(attempts, 1)
    delay = min(BACKOFF_BASE * (2 ** (n - 1)), BACKOFF_CAP)
    return now + delay


def is_dead(locked_at: datetime | None, now: datetime) -> bool:
    """running 超过 DEAD_TASK_TIMEOUT 视为僵死（认领的 worker 已不在）。"""
    if locked_at is None:
        return False
    return now - locked_at > DEAD_TASK_TIMEOUT


def should_retry(attempts: int, max_attempts: int) -> bool:
    return attempts < max_attempts
