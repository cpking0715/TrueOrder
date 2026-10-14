"""AI 买家发现：从品名/行业生成真实进口商名单（纯函数：提示词+解析）。"""

from __future__ import annotations

import json
import re

from app.domain.entities import DiscoveredBuyer

_DISCOVER_PROMPT = (
    "List 20 real, verifiable companies that import or wholesale "
    "the following product in the United States. "
    "Only include companies you are confident actually exist. "
    "Output a JSON array, each element:\n"
    '{{"company_name": "legal name", "city": "city", '
    '"state": "2-letter state code", "note": "brief reason"}}\n'
    "Rules:\n"
    "- Only real companies, no fabrication\n"
    "- Mid-size importers/wholesalers/distributors preferred\n"
    "- Output ONLY the JSON array\n"
    "Product: {category} (HS code: {hs_code})"
)


def build_discover_messages(category: str, hs_code: str = "") -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": _DISCOVER_PROMPT.format(category=category, hs_code=hs_code or "N/A"),
        }
    ]


def parse_discover_response(content: str | None) -> list[DiscoveredBuyer]:
    """解析 AI 返回的公司列表；剥围栏→JSON→逐条校验；空/畸形返回空。"""
    if not content:
        return []
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    # 找 JSON 数组（AI 可能在前后加解释文字）
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        rows = json.loads(match.group())
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(rows, list):
        return []
    result: list[DiscoveredBuyer] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("company_name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        city_parts = [str(row.get("city") or "").strip(), str(row.get("state") or "").strip()]
        city = ", ".join(p for p in city_parts if p)
        result.append(
            DiscoveredBuyer(
                company_name=name,
                country="US",
                city=city,
                note=str(row.get("note") or "").strip()[:200],
            )
        )
    return result
