"""统一的 LLM 客户端（DeepSeek / OpenAI 兼容 chat/completions）与 AI 日额度。

所有 AI 调用（税号推荐、买家发现、官网联系人提取）都走这里：
- 统一 URL/鉴权头/超时；HTTP、网络、响应解析错误统一转为 LlmError；
- AiQuota：按 UTC 自然日统计 enrichment_calls 里 provider 以 ``ai-`` 开头的调用，
  与 TRUEORDER_AI_DAILY_CAP 比较；每次外呼记一行审计（credits_used=0，不占补全额度）。

测试替换：monkeypatch ``app.infrastructure.llm_client.httpx.post``，或构造时传 ``post=``。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.timeutil import utc_day_bounds
from app.infrastructure.orm import EnrichmentCallORM

log = get_logger("app.llm")

AI_PROVIDER_PREFIX = "ai-"


class LlmError(Exception):
    """AI 服务调用失败（网络/HTTP 状态/响应格式）。"""


class LlmNotConfigured(LlmError):
    """未配置 TRUEORDER_AI_API_KEY。"""


class LlmClient:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 30.0,
        post: Callable[..., Any] | None = None,
    ) -> None:
        if not api_key:
            raise LlmNotConfigured("未配置 AI Key（TRUEORDER_AI_API_KEY）")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._post = post

    @classmethod
    def from_settings(cls, settings: Settings, timeout: float = 30.0) -> LlmClient:
        return cls(
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            base_url=settings.ai_base_url,
            timeout=timeout,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0,
        max_tokens: int = 2000,
        disable_thinking: bool = True,
        timeout: float | None = None,
    ) -> str:
        """返回首个 choice 的 content（去首尾空白，可能为空串）。"""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if disable_thinking:
            # 推理模型思维链会随机膨胀吃光 max_tokens（content 为空）；分类/提取任务无需推理
            payload["thinking"] = {"type": "disabled"}
        post = self._post or httpx.post
        try:
            response = post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=timeout or self._timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            log.warning("llm http error", extra={"error": f"{type(exc).__name__}: {exc}"})
            raise LlmError(f"AI 服务调用失败：{type(exc).__name__}") from exc
        except ValueError as exc:
            raise LlmError("AI 服务返回的不是 JSON") from exc
        try:
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        except (AttributeError, IndexError, TypeError) as exc:
            raise LlmError("AI 服务响应格式不符") from exc
        return (content or "").strip()


class AiQuota:
    """AI 调用日额度（UTC 自然日，所有 ai-* provider 合计）。"""

    def __init__(self, session: Session, daily_cap: int) -> None:
        self._session = session
        self._cap = daily_cap

    def used_today(self) -> int:
        start, end = utc_day_bounds()
        return int(
            self._session.scalar(
                select(func.count()).select_from(EnrichmentCallORM).where(
                    EnrichmentCallORM.provider.startswith(AI_PROVIDER_PREFIX),
                    EnrichmentCallORM.called_at >= start,
                    EnrichmentCallORM.called_at < end,
                )
            )
            or 0
        )

    def remaining(self) -> int:
        return max(self._cap - self.used_today(), 0)

    def record(self, provider: str, company_id: int | None = None, ok: bool = True) -> None:
        """记一次 AI 外呼（只 add，不提交；由调用方事务提交）。"""
        if not provider.startswith(AI_PROVIDER_PREFIX):
            raise ValueError(f"AI 配额只记 {AI_PROVIDER_PREFIX}* 供应方：{provider}")
        self._session.add(
            EnrichmentCallORM(
                provider=provider, company_id=company_id, credits_used=0, ok=ok
            )
        )
