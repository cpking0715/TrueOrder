"""后台任务 worker：`uv run python -m app.worker` 轮询认领并执行队列任务。

处理器注册表见 app.infrastructure.enrichment.build_registry：
find_contacts / crawl_website / verify_email（verify 仅配置 Hunter Key 后产生）。
未知类型的任务会被永久标记 failed 并写明原因，便于在任务状态页发现配置遗漏。
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.infrastructure.db import make_engine, make_session_factory
from app.infrastructure.jobs import Handler, SqlJobQueue, Worker


def build_handlers() -> dict[str, Handler]:
    """WP4 处理器注册表；第二期再挂 send_email / poll_imap。"""
    from app.infrastructure.enrichment import build_registry

    return build_registry()


def run_loop(
    factory: sessionmaker[Session],
    handlers: dict[str, Callable[[Session, dict], None]],
    interval: float = 2.0,
    once: bool = False,
) -> None:
    while True:
        session = factory()
        try:
            worker = Worker(SqlJobQueue(session), handlers)
            worker.run_once(datetime.now(UTC))
        finally:
            session.close()
        if once:
            return
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="TrueOrder 后台任务 worker")
    parser.add_argument("--once", action="store_true", help="只跑一轮即退出（调试用）")
    parser.add_argument("--interval", type=float, default=2.0, help="轮询间隔秒数")
    args = parser.parse_args()

    engine = make_engine(get_settings().database_url)
    factory = make_session_factory(engine)
    handlers = build_handlers()
    names = sorted(handlers) or "（无，WP4 接入）"
    print(f"worker 启动：handlers={names}，interval={args.interval}s")
    try:
        run_loop(factory, handlers, interval=args.interval, once=args.once)
    except KeyboardInterrupt:
        print("worker 已停止")


if __name__ == "__main__":
    main()
