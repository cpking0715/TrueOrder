"""API 令牌鉴权：设置 TRUEORDER_API_TOKEN 后 /api 必须带令牌；/healthz 不鉴权。"""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings
from app.interface.auth import require_api_token

TOKEN = "s3cret-token"


@pytest.fixture()
def secured(client):
    client.app.dependency_overrides.pop(require_api_token, None)
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        api_token=TOKEN, _env_file=None
    )
    return client


def test_无令牌401(secured):
    r = secured.get("/api/products")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_错误令牌401(secured):
    assert secured.get("/api/products", headers={"X-API-Token": "nope"}).status_code == 401


@pytest.mark.parametrize(
    "kwargs",
    [
        {"headers": {"Authorization": f"Bearer {TOKEN}"}},
        {"headers": {"X-API-Token": TOKEN}},
        {"params": {"api_token": TOKEN}},
    ],
)
def test_三种携带方式均可(secured, kwargs):
    assert secured.get("/api/products", **kwargs).status_code == 200


def test_写接口同样受保护(secured):
    r = secured.post("/api/products", json={"name": "x", "hs_code": "620462"})
    assert r.status_code == 401


def test_healthz不鉴权且检查数据库(secured):
    r = secured.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_未设置令牌时鉴权关闭(client):
    client.app.dependency_overrides.pop(require_api_token, None)
    client.app.dependency_overrides[get_settings] = lambda: Settings(api_token="", _env_file=None)
    assert client.get("/api/products").status_code == 200


def test_响应带RequestID(client):
    r = client.get("/api/products", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
