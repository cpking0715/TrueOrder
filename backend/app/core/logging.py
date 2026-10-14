"""结构化日志：单行 JSON 输出到 stderr，自动带上当前 request_id / job_id。

用法：
    from app.core.logging import configure_logging, get_logger
    configure_logging()          # 进程入口调用一次（API 与 worker）
    log = get_logger(__name__)
    log.info("job done", extra={"kind": "send_email"})

上下文字段通过 contextvars 传递：API 中间件设置 request_id，worker 设置 job_id。
级别由 TRUEORDER_LOG_LEVEL 控制（默认 INFO）。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_var: ContextVar[int | None] = ContextVar("job_id", default=None)

# LogRecord 自带属性，不作为 extra 字段输出
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if (rid := request_id_var.get()) is not None:
            payload["request_id"] = rid
        if (jid := job_id_var.get()) is not None:
            payload["job_id"] = jid
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def configure_logging(level: str | None = None) -> None:
    """幂等：重复调用不重复挂 handler。"""
    global _configured
    root = logging.getLogger()
    root.setLevel((level or os.environ.get("TRUEORDER_LOG_LEVEL") or "INFO").upper())
    if _configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
