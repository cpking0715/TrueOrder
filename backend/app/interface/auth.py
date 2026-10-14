"""API 访问令牌：TRUEORDER_API_TOKEN 设置后，所有 /api 路由都必须带令牌。

令牌可放在以下任一位置（按顺序取第一个）：
- 请求头 ``Authorization: Bearer <token>``
- 请求头 ``X-API-Token: <token>``
- 查询参数 ``api_token=<token>``：仅供浏览器直接下载 CSV 用（<a href> 带不了请求头）

TRUEORDER_API_TOKEN 为空表示关闭鉴权：只适合本机开发/演示（默认只监听 127.0.0.1），
启动时会打 warning。对外暴露（非本机访问）前必须设置。
"""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings


def _supplied_token(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.headers.get("x-api-token") or request.query_params.get("api_token") or None


def require_api_token(request: Request, settings: Settings = Depends(get_settings)) -> None:
    expected = settings.api_token
    if not expected:
        return
    supplied = _supplied_token(request)
    if supplied is None or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(
            status_code=401,
            detail="缺少或错误的 API 令牌（TRUEORDER_API_TOKEN）",
            headers={"WWW-Authenticate": "Bearer"},
        )
