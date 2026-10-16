"""开发信草稿的 LLM 实现（实现领域端口 DraftWriter）。只生成文案，不发送。

失败（未配 Key、超日额度、网络、格式）一律抛异常，由领域 generate_draft 回落模板。
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.kit_sales import DraftContext, DraftText
from app.infrastructure.llm_client import AiQuota, LlmClient, LlmError

PROVIDER = "ai-kit-draft"

_SYSTEM = (
    "You write short, polite B2B cold outreach for a Chinese kidswear manufacturer. "
    "No false urgency, no fake claims, no attachments. "
    'Reply ONLY with JSON: {"subject": "...", "body": "..."}. '
    "For WhatsApp, subject must be empty and body under 60 words."
)


class LlmDraftWriter:
    def __init__(self, client: LlmClient, quota: AiQuota) -> None:
        self._client = client
        self._quota = quota

    @classmethod
    def from_settings(cls, settings: Settings, session: Session) -> LlmDraftWriter:
        return cls(LlmClient.from_settings(settings), AiQuota(session, settings.ai_daily_cap))

    def write(self, ctx: DraftContext) -> DraftText:
        if self._quota.remaining() <= 0:
            raise LlmError("AI 日额度已用完")
        user = json.dumps(
            {
                "channel": ctx.channel, "buyer_company": ctx.company, "country": ctx.country,
                "contact_name": ctx.contact_name, "product": ctx.product, "specs": ctx.specs,
                "moq": ctx.moq, "lead_time_days": ctx.lead_time_days,
                "selling_points": list(ctx.selling_points), "sender_name": ctx.sender_name,
            },
            ensure_ascii=False,
        )
        ok = False
        try:
            raw = self._client.chat(
                [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
                temperature=0.4, max_tokens=800,
            )
            data = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            ok = True
            return DraftText(subject=str(data.get("subject", "")), body=str(data["body"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmError(f"AI 草稿格式不对：{exc}") from exc
        finally:
            self._quota.record(PROVIDER, ok=ok)
