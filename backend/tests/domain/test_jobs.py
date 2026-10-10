"""后台任务领域规则：指数退避、僵死判定、重试边界（纯函数，零 mock）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.jobs import DEAD_TASK_TIMEOUT, is_dead, next_run_after, should_retry

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)


class Test指数退避:
    def test_首次失败等一分钟(self):
        assert next_run_after(1, NOW) == NOW + timedelta(seconds=60)

    def test_逐次翻倍(self):
        assert next_run_after(2, NOW) == NOW + timedelta(seconds=120)
        assert next_run_after(3, NOW) == NOW + timedelta(seconds=240)
        assert next_run_after(4, NOW) == NOW + timedelta(seconds=480)

    def test_封顶一小时(self):
        assert next_run_after(10, NOW) == NOW + timedelta(hours=1)

    def test_零次失败按首次计(self):
        assert next_run_after(0, NOW) == NOW + timedelta(seconds=60)


class Test僵死判定:
    def test_锁定超过十分钟为僵死(self):
        assert is_dead(NOW - DEAD_TASK_TIMEOUT - timedelta(seconds=1), NOW) is True

    def test_锁定不足十分钟不判死(self):
        assert is_dead(NOW - timedelta(minutes=9), NOW) is False

    def test_未锁定不判死(self):
        assert is_dead(None, NOW) is False


class Test重试边界:
    def test_未达上限可重试(self):
        assert should_retry(2, 3) is True

    def test_达到上限不再重试(self):
        assert should_retry(3, 3) is False
