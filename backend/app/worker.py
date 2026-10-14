"""后台任务 worker：`uv run python -m app.worker` 轮询认领并执行队列任务。

处理器注册表见 app.infrastructure.enrichment.build_registry：
find_contacts / crawl_website / verify_email（仅配 Hunter Key 后产生）；
send_email / import_csv 在 build_handlers 另行注册。
未知类型的任务会被永久标记 failed 并写明原因，便于在任务状态页发现配置遗漏。
"""

from __future__ import annotations

import argparse
import os
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings, require_configured_database
from app.core.logging import configure_logging, get_logger
from app.infrastructure.db import make_engine, make_session_factory
from app.infrastructure.jobs import Handler, SqlJobQueue, Worker

log = get_logger("app.worker")


def build_handlers() -> dict[str, Handler]:
    """处理器注册表：免费目录源（Wikidata 域名发现）+ 计量 finder + 官网抓取。"""
    from app.infrastructure.enrichment import build_registry
    from app.infrastructure.website_directory import WikidataDirectory

    registry = build_registry(directory=WikidataDirectory())
    from app.infrastructure.outreach import make_send_email_handler
    registry["send_email"] = make_send_email_handler()
    from app.infrastructure.import_jobs import make_import_csv_handler

    registry["import_csv"] = make_import_csv_handler()
    return registry


# 秒：心跳在每轮与每个任务之间刷新；超过即视为卡死（单任务执行时间应远小于此）
HEARTBEAT_MAX_AGE = 300.0


def touch_heartbeat(path: str | None) -> None:
    if path:
        Path(path).touch()


def heartbeat_ok(path: str, max_age: float = HEARTBEAT_MAX_AGE, now: float | None = None) -> bool:
    """容器健康检查：心跳文件存在且足够新。"""
    try:
        mtime = Path(path).stat().st_mtime
    except FileNotFoundError:
        return False
    return ((now if now is not None else time.time()) - mtime) <= max_age


def run_loop(
    factory: sessionmaker[Session],
    handlers: dict[str, Handler],
    interval: float = 2.0,
    once: bool = False,
    stop: threading.Event | None = None,
    heartbeat: str | None = None,
) -> None:
    """轮询循环；stop 被置位后在当前任务结束时退出（不打断执行中的任务）。"""
    stop = stop or threading.Event()
    while not stop.is_set():
        touch_heartbeat(heartbeat)
        session = factory()
        try:
            worker = Worker(SqlJobQueue(session), handlers)
            def should_stop() -> bool:
                touch_heartbeat(heartbeat)
                return stop.is_set()

            worker.run_once(datetime.now(UTC), should_stop=should_stop)
        finally:
            session.close()
        if once:
            return
        stop.wait(interval)


def install_signal_handlers(stop: threading.Event) -> None:
    """SIGTERM / SIGINT → 置位 stop，跑完当前任务后退出（容器/进程托管优雅停止）。"""

    def _handle(signum, _frame):
        log.info("收到停止信号，当前任务完成后退出", extra={"signal": signal.Signals(signum).name})
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="TrueOrder 后台任务 worker")
    parser.add_argument("--once", action="store_true", help="只跑一轮即退出（调试用）")
    parser.add_argument("--interval", type=float, default=2.0, help="轮询间隔秒数")
    parser.add_argument(
        "--heartbeat-file",
        default=os.environ.get("TRUEORDER_WORKER_HEARTBEAT"),
        help="心跳文件路径（容器健康检查用；默认读 TRUEORDER_WORKER_HEARTBEAT）",
    )
    parser.add_argument(
        "--check-heartbeat", action="store_true", help="只检查心跳是否新鲜（退出码 0/1）"
    )
    args = parser.parse_args()
    if args.check_heartbeat:
        raise SystemExit(0 if args.heartbeat_file and heartbeat_ok(args.heartbeat_file) else 1)

    configure_logging()
    require_configured_database()
    engine = make_engine(get_settings().database_url)
    factory = make_session_factory(engine)
    handlers = build_handlers()
    stop = threading.Event()
    install_signal_handlers(stop)
    log.info("worker 启动", extra={"handlers": sorted(handlers), "interval": args.interval})
    run_loop(
        factory,
        handlers,
        interval=args.interval,
        once=args.once,
        stop=stop,
        heartbeat=args.heartbeat_file,
    )
    log.info("worker 已停止")


if __name__ == "__main__":
    main()
