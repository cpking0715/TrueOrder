"""后台任务 worker：`uv run python -m app.worker` 轮询认领并执行队列任务。

处理器注册表见 app.infrastructure.enrichment.build_registry：
find_contacts / crawl_website / verify_email（verify 仅配置 Hunter Key 后产生）。
未知类型的任务会被永久标记 failed 并写明原因，便于在任务状态页发现配置遗漏。
"""

from __future__ import annotations

import argparse
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime

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
    return registry


def run_loop(
    factory: sessionmaker[Session],
    handlers: dict[str, Callable[[Session, dict], None]],
    interval: float = 2.0,
    once: bool = False,
    stop: threading.Event | None = None,
) -> None:
    """轮询循环；stop 被置位后在当前任务结束时退出（不打断执行中的任务）。"""
    stop = stop or threading.Event()
    while not stop.is_set():
        session = factory()
        try:
            worker = Worker(SqlJobQueue(session), handlers)
            worker.run_once(datetime.now(UTC), should_stop=stop.is_set)
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
    args = parser.parse_args()

    configure_logging()
    require_configured_database()
    engine = make_engine(get_settings().database_url)
    factory = make_session_factory(engine)
    handlers = build_handlers()
    stop = threading.Event()
    install_signal_handlers(stop)
    log.info("worker 启动", extra={"handlers": sorted(handlers), "interval": args.interval})
    run_loop(factory, handlers, interval=args.interval, once=args.once, stop=stop)
    log.info("worker 已停止")


if __name__ == "__main__":
    main()
