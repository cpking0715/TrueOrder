"""read_csv_upload 共用依赖：上限 413、非法 Content-Length 400、非 UTF-8 422（不连库）。"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.interface.deps import read_csv_upload


def _call(data: bytes, content_length: str | None = None, max_mb: int = 1):
    headers = {} if content_length is None else {"content-length": content_length}
    file = SimpleNamespace(file=io.BytesIO(data), filename="a.csv")
    request = SimpleNamespace(headers=headers)
    return read_csv_upload(file, request, Settings(max_upload_mb=max_mb, _env_file=None))


def test_正常读取并去BOM():
    up = _call("\ufeffa,b\n1,2\n".encode())
    assert up.text == "a,b\n1,2\n" and up.filename == "a.csv"


@pytest.mark.parametrize("bad", ["abc", "", "1.5", "-x"])
def test_非法ContentLength返回400(bad):
    with pytest.raises(HTTPException) as exc:
        _call(b"a,b\n", content_length=bad)
    assert exc.value.status_code == 400


def test_声明超限返回413():
    with pytest.raises(HTTPException) as exc:
        _call(b"a", content_length=str(2 * 1024 * 1024))
    assert exc.value.status_code == 413


def test_实际超限返回413():
    with pytest.raises(HTTPException) as exc:
        _call(b"x" * (1024 * 1024 + 1))
    assert exc.value.status_code == 413


def test_非UTF8返回422():
    with pytest.raises(HTTPException) as exc:
        _call("名称".encode("gbk"))
    assert exc.value.status_code == 422
