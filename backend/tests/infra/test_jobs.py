"""任务队列（真 PostgreSQL）：认领互斥、退避、僵死回收、worker 分发。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.jobs import Job
from app.infrastructure.jobs import SqlJobQueue, Worker

# 动态基准时间（略超前）：入队默认 run_after=now()，固定日期会在跨天后让任务永不到期
NOW = datetime.now(UTC) + timedelta(hours=1)  # 余量放大：全量套件运行数十秒，5 秒会过期


@pytest.fixture()
def queue(session: Session) -> SqlJobQueue:
    return SqlJobQueue(session)


class Test入队与认领:
    def test_入队默认立即可认领并置running(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {"company_id": 1})
        jobs = queue.claim(NOW)
        assert [j.id for j in jobs] == [job_id]
        assert jobs[0].status == "running"
        assert jobs[0].locked_at == NOW

    def test_run_after未到期不认领(self, queue: SqlJobQueue):
        queue.enqueue("find_contacts", {}, run_after=NOW + timedelta(minutes=5))
        assert queue.claim(NOW) == []

    def test_到期后可认领(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {}, run_after=NOW + timedelta(minutes=5))
        later = NOW + timedelta(minutes=6)
        assert [j.id for j in queue.claim(later)] == [job_id]

    def test_批量认领按run_after先后(self, queue: SqlJobQueue):
        late = queue.enqueue("find_contacts", {}, run_after=NOW + timedelta(minutes=2))
        early = queue.enqueue("crawl_website", {}, run_after=NOW + timedelta(minutes=1))
        jobs = queue.claim(NOW + timedelta(minutes=3), limit=10)
        assert [j.id for j in jobs] == [early, late]

    def test_running不再被认领(self, queue: SqlJobQueue):
        queue.enqueue("find_contacts", {})
        queue.claim(NOW)
        assert queue.claim(NOW) == []

    def test_两worker交错认领不重复(self, session: Session, engine):
        other = Session(engine)
        q1, q2 = SqlJobQueue(session), SqlJobQueue(other)
        ids = {q1.enqueue("find_contacts", {"n": n}) for n in range(6)}
        claimed: list[int] = []
        while True:
            batch = q1.claim(NOW, limit=2) + q2.claim(NOW, limit=2)
            if not batch:
                break
            claimed.extend(j.id for j in batch)
        other.close()
        assert len(claimed) == len(set(claimed)) == len(ids)


class Test完成与失败:
    def test_完成后状态done(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {})
        queue.claim(NOW)
        queue.complete(job_id)
        done = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert done.status == "done"
        # done 不再被认领
        assert queue.claim(NOW + timedelta(minutes=1)) == []

    def test_失败未达上限回pending并退避(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {}, max_attempts=3)
        queue.claim(NOW)
        queue.fail(job_id, "boom", NOW + timedelta(seconds=30))
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "pending"
        assert job.attempts == 1
        assert job.last_error == "boom"
        # 失败发生在 NOW+30s，第一次退避 60s → NOW+90s 后才可再认领
        assert queue.claim(NOW + timedelta(seconds=70)) == []
        assert queue.claim(NOW + timedelta(seconds=95))

    def test_失败达到上限置failed(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {}, max_attempts=1)
        queue.claim(NOW)
        queue.fail(job_id, "boom", NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "failed"
        assert job.attempts == 1

    def test_永久失败不重试(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {}, max_attempts=5)
        queue.claim(NOW)
        queue.fail_permanent(job_id, "unknown job kind")
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "failed"
        assert queue.claim(NOW + timedelta(hours=2)) == []


class Test僵死回收:
    def test_超时running回收为pending并计数(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {}, max_attempts=3)
        queue.claim(NOW)
        recovered = queue.recover_dead(NOW + timedelta(minutes=11))
        assert recovered == 1
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "pending"
        assert job.attempts == 1

    def test_回收达到上限置failed(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {}, max_attempts=1)
        queue.claim(NOW)
        queue.recover_dead(NOW + timedelta(minutes=11))
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "failed"

    def test_未超时不回收(self, queue: SqlJobQueue):
        queue.enqueue("find_contacts", {})
        queue.claim(NOW)
        assert queue.recover_dead(NOW + timedelta(minutes=5)) == 0


class TestWorker分发:
    def test_成功任务置done(self, queue: SqlJobQueue, session: Session):
        seen: list[dict] = []

        def handler(sess: Session, payload: dict) -> None:
            seen.append(payload)

        job_id = queue.enqueue("find_contacts", {"company_id": 9})
        worker = Worker(queue, {"find_contacts": handler})
        assert worker.run_once(NOW) == 1
        assert seen == [{"company_id": 9}]
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "done"

    def test_处理器抛错走失败退避(self, queue: SqlJobQueue):
        def boom(sess: Session, payload: dict) -> None:
            raise RuntimeError("network down")

        job_id = queue.enqueue("crawl_website", {}, max_attempts=3)
        Worker(queue, {"crawl_website": boom}).run_once(NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "pending"
        assert "network down" in (job.last_error or "")

    def test_未知类型永久失败(self, queue: SqlJobQueue):
        job_id = queue.enqueue("send_email", {})
        Worker(queue, {}).run_once(NOW)
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "failed"
        assert "unknown" in (job.last_error or "").lower()

    def test_run_once先回收僵死再认领(self, queue: SqlJobQueue):
        job_id = queue.enqueue("find_contacts", {}, max_attempts=3)
        queue.claim(NOW)  # 认领后 worker “死了”
        Worker(queue, {"find_contacts": lambda s, p: None}).run_once(
            NOW + timedelta(minutes=11)
        )
        job = [j for j in queue.list_jobs() if j.id == job_id][0]
        assert job.status == "done"

    def test_list_jobs按状态过滤(self, queue: SqlJobQueue):
        queue.enqueue("find_contacts", {})
        queue.enqueue("crawl_website", {})
        queue.claim(NOW)  # 认领最早的一条
        running = queue.list_jobs(status="running")
        pending = queue.list_jobs(status="pending")
        assert len(running) == 1
        assert len(pending) == 1
        assert isinstance(pending[0], Job)
