"""统一 LLM 客户端与 AI 日额度。"""

from __future__ import annotations

import httpx
import pytest

from app.infrastructure.llm_client import AiQuota, LlmClient, LlmError, LlmNotConfigured


class _Resp:
    def __init__(self, body=None, status=200, raw=None):
        self._body, self.status_code, self._raw = body, status, raw

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("POST", "https://x")
            raise httpx.HTTPStatusError("err", request=req, response=httpx.Response(500))

    def json(self):
        if self._raw is not None:
            raise ValueError("not json")
        return self._body


def _client(resp, captured=None):
    def post(url, json=None, headers=None, timeout=None):
        if captured is not None:
            captured.update(url=url, json=json, headers=headers, timeout=timeout)
        if isinstance(resp, Exception):
            raise resp
        return resp

    return LlmClient(api_key="k", base_url="https://api.x/", post=post, timeout=7)


def test_请求载荷与返回内容():
    captured: dict = {}
    out = _client(_Resp({"choices": [{"message": {"content": " 620462 \n"}}]}), captured).chat(
        [{"role": "user", "content": "hi"}]
    )
    assert out == "620462"
    assert captured["url"] == "https://api.x/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["timeout"] == 7


def test_可保留推理模式():
    captured: dict = {}
    _client(_Resp({"choices": [{"message": {"content": "x"}}]}), captured).chat(
        [], disable_thinking=False
    )
    assert "thinking" not in captured["json"]


@pytest.mark.parametrize(
    "resp",
    [
        httpx.ConnectTimeout("t"),
        _Resp(status=500),
        _Resp(raw="<html>"),
        _Resp({"choices": "oops"}),
    ],
)
def test_各类失败统一为LlmError(resp):
    with pytest.raises(LlmError):
        _client(resp).chat([])


def test_空内容返回空串():
    assert _client(_Resp({"choices": [{"message": {"content": None}}]})).chat([]) == ""


def test_无Key抛未配置():
    with pytest.raises(LlmNotConfigured):
        LlmClient(api_key="")


def test_AI额度合计所有ai前缀provider(session):
    from app.infrastructure.enrichment import SqlEnrichmentLog

    quota = AiQuota(session, daily_cap=3)
    quota.record("ai-hs")
    quota.record("ai-discover")
    session.commit()
    assert quota.used_today() == 2
    assert quota.remaining() == 1
    # 非 AI 的补全调用不计入 AI 额度
    from app.infrastructure.orm import CompanyORM

    company = CompanyORM(normalized_name="ACME", country="US", name_variants=["Acme"])
    session.add(company)
    session.flush()
    SqlEnrichmentLog(session).record("fake", company.id)
    session.commit()
    assert quota.used_today() == 2
