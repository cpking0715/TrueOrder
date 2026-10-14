"""时间工具：「当日」一律按 UTC 自然日计算。

不要用 SQL 的 ``date(col)`` / ``current_date``：它们取 PostgreSQL 会话时区，
与应用侧 ``datetime.now(UTC)`` 不一致，在本地零点附近（如 UTC+8 的 00:00–08:00）
会把当天的记录算到「昨天」，导致日额度计数漂移。改用 UTC 半开区间过滤。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta


def utc_today() -> date:
    return datetime.now(UTC).date()


def utc_day_bounds(day: date | None = None) -> tuple[datetime, datetime]:
    """返回 UTC 自然日的半开区间 [start, end)。"""
    day = day or utc_today()
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)
