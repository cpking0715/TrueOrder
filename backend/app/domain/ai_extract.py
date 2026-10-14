"""AI 页面联系人提取：提示词构造与响应解析（纯函数，DeepSeek 适配器共用）。

模型只做「结构化」——从已有页面文本里抽姓名/职位/邮箱/电话，
不做推断或补全（防幻觉：邮箱必须原文出现）。
"""

from __future__ import annotations

import json

from app.domain.entities import FoundContact

_SYSTEM_PROMPT = (
    "你是联系人信息提取器。从给定网页文本中抽取真实存在的联系人，"
    "输出严格 JSON 数组，每个元素形如 "
    '{"name": "姓名或null", "title": "职位或空串", "email": "邮箱", "phone": "电话或null"}。'
    "规则：只抽文本中原文出现过的信息，不得推断、猜测或补全；"
    "邮箱/电话必须逐字符来自原文；通用邮箱（info@/sales@ 等）name 用 null；"
    "没有联系人时输出 []。只输出 JSON，不要任何解释或代码块标记。"
)


def build_extract_messages(page_text: str, url: str) -> list[dict[str, str]]:
    """构造 chat messages；页面文本截断防 token 失控。"""
    trimmed = (page_text or "")[:12000]
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"页面 URL：{url}\n\n页面文本：\n{trimmed}"},
    ]


def parse_extract_response(content: str | None) -> list[FoundContact]:
    """解析模型输出：剥代码块围栏→JSON 数组→FoundContact；任何异常返回空。"""
    if not content:
        return []
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        rows = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(rows, list):
        return []
    contacts: list[FoundContact] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        email = str(row.get("email") or "").strip()
        if not email or "@" not in email or email.lower() in seen:
            continue
        seen.add(email.lower())
        name = str(row.get("name") or "").strip() or None
        if name and name.lower() in ("null", "none", "n/a"):
            name = None
        contacts.append(
            FoundContact(
                name=name,
                title=str(row.get("title") or "").strip(),
                email=email,
                phone=str(row.get("phone") or "").strip() or None,
                source_ref="",  # 调用方回填 URL
            )
        )
    return contacts
