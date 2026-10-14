"""worker 心跳：容器健康检查依据。"""

from __future__ import annotations

import os
import threading

from app.worker import heartbeat_ok, run_loop, touch_heartbeat


def test_无心跳文件不健康(tmp_path):
    assert heartbeat_ok(str(tmp_path / "missing")) is False


def test_新心跳健康_过期不健康(tmp_path):
    hb = tmp_path / "hb"
    touch_heartbeat(str(hb))
    assert heartbeat_ok(str(hb)) is True
    old = hb.stat().st_mtime - 1000
    os.utime(hb, (old, old))
    assert heartbeat_ok(str(hb), max_age=300) is False


def test_轮询循环刷新心跳(tmp_path, engine):
    from app.infrastructure.db import make_session_factory

    hb = tmp_path / "hb"
    run_loop(make_session_factory(engine), {}, once=True, stop=threading.Event(), heartbeat=str(hb))
    assert heartbeat_ok(str(hb))
