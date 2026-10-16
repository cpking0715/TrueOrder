"""LLM 草稿适配器（真 PG 记审计）：解析 JSON、格式错误抛 LlmError、额度用尽不外呼。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.domain.kit_sales import DraftContext, generate_draft
from app.infrastructure.kit_llm import PROVIDER, LlmDraftWriter
from app.infrastructure.llm_client import AiQuota, LlmClient, LlmError
from app.infrastructure.orm import EnrichmentCallORM

CTX = DraftContext("email", "Tiny Kids", "US", "Amy", "Romper", "cotton", 300, 30, ("GOTS",), "")


class _Resp:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


def _writer(session, content: str, cap: int = 10) -> tuple[LlmDraftWriter, list]:
    calls: list = []

    def post(url, **kw):
        calls.append(kw["json"])
        return _Resp(content)

    return LlmDraftWriter(LlmClient(api_key="k", post=post), AiQuota(session, cap)), calls


def test_解析围栏JSON并记一次审计(session):
    body = json.dumps({"subject": "Hi", "body": "Hello Amy"})
    writer, calls = _writer(session, f"```json\n{body}\n```")
    got = writer.write(CTX)
    assert got.subject == "Hi" and got.body == "Hello Amy"
    session.commit()
    rows = session.scalars(select(EnrichmentCallORM)).all()
    assert [(r.provider, r.ok, r.credits_used) for r in rows] == [(PROVIDER, True, 0)]
    assert "Romper" in calls[0]["messages"][1]["content"]


def test_格式错误抛LlmError_领域回落模板(session):
    writer, _ = _writer(session, "not json")
    with pytest.raises(LlmError):
        writer.write(CTX)
    assert generate_draft(CTX, writer)[1] == "template"


def test_额度用尽不外呼(session):
    writer, calls = _writer(session, "{}", cap=0)
    with pytest.raises(LlmError):
        writer.write(CTX)
    assert calls == []
