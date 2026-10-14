"""DeepSeek 页面联系人提取适配器（OpenAI 兼容 chat/completions，HTTP 注入可测）。

仅当 TRUEORDER_AI_API_KEY 配置时由 handler 启用；网络/解析失败向上抛，
由爬虫侧兜底（AI 是增强，不是依赖）。
"""

from __future__ import annotations

from app.domain.ai_extract import build_extract_messages, parse_extract_response
from app.domain.entities import FoundContact
from app.infrastructure.llm_client import LlmClient


class DeepSeekExtractor:
    """fetch(url, payload) -> dict 可注入（测试用）；默认走统一 LlmClient。"""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 30.0,
        fetch=None,
    ) -> None:
        self._fetch = fetch
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = LlmClient(api_key=api_key, model=model, base_url=base_url, timeout=timeout)
        self.calls = 0  # 单实例调用计数（审计用）

    def extract(self, page_text: str, url: str) -> list[FoundContact]:
        messages = build_extract_messages(page_text, url)
        if self._fetch is not None:
            payload = {
                "model": self._model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": 2000,
                "thinking": {"type": "disabled"},
            }
            data = self._fetch(f"{self._base_url}/chat/completions", payload)
            content = (data or {}).get("choices", [{}])[0].get("message", {}).get("content")
        else:
            content = self._client.chat(messages, temperature=0, max_tokens=2000)
        self.calls += 1
        return parse_extract_response(content)


def make_ai_extractor(settings) -> DeepSeekExtractor | None:
    """有 key 才建；无 key 返回 None（走纯正则，界面提示未配置）。"""
    if not settings.ai_api_key:
        return None
    return DeepSeekExtractor(
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        base_url=settings.ai_base_url,
    )
