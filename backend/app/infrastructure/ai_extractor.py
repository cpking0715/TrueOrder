"""DeepSeek 页面联系人提取适配器（OpenAI 兼容 chat/completions，HTTP 注入可测）。

仅当 TRUEORDER_AI_API_KEY 配置时由 handler 启用；网络/解析失败向上抛，
由爬虫侧兜底（AI 是增强，不是依赖）。
"""

from __future__ import annotations

from app.domain.ai_extract import build_extract_messages, parse_extract_response
from app.domain.entities import FoundContact


class DeepSeekExtractor:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 30.0,
        fetch=None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._fetch = fetch or self._http_post
        self.calls = 0  # 单实例调用计数（审计用）

    def extract(self, page_text: str, url: str) -> list[FoundContact]:
        payload = {
            "model": self._model,
            "messages": build_extract_messages(page_text, url),
            "temperature": 0,
            "max_tokens": 2000,
            # 推理模型思维链会吃光 max_tokens 致 content 为空，结构化提取无需推理
            "thinking": {"type": "disabled"},
        }
        data = self._fetch(f"{self._base_url}/chat/completions", payload)
        self.calls += 1
        content = (data or {}).get("choices", [{}])[0].get("message", {}).get("content")
        return parse_extract_response(content)

    def _http_post(self, url: str, payload: dict) -> dict:
        import httpx

        response = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()


def make_ai_extractor(settings) -> DeepSeekExtractor | None:
    """有 key 才建；无 key 返回 None（走纯正则，界面提示未配置）。"""
    if not settings.ai_api_key:
        return None
    return DeepSeekExtractor(
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        base_url=settings.ai_base_url,
    )
