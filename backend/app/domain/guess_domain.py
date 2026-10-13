"""域名猜测：从公司名生成常见域名候选（纯函数，供批量尝试）。"""

from __future__ import annotations

import re

from app.domain.normalize import normalize_company_name

_STOP_WORDS = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
    "co", "company", "llp", "lp", "gmbh", "ag", "sa", "sas", "bv", "nv",
    "plc", "pt", "tbk", "pte", "sdn", "bhd", "kk", "oy", "ab", "spa", "srl",
    "jsc", "group", "holdings", "holding", "usa", "us", "international",
    "the", "and", "of", "a", "an",
}

_TLDS = ("com", "com", "com", "net")  # com 优先级更高


def guess_domains(company_name: str, max_candidates: int = 4) -> list[str]:
    """从公司名生成常见域名候选，按可能性排序。

    规则：去法律后缀/停用词 → 取核心词 → 拼常用模式：
    - 全词连写：karenkane.com
    - 首字母缩写+末词：kkane.com
    - 首词+末词首字母：karenk.com
    """
    normalized = normalize_company_name(company_name)
    if not normalized:
        return []

    words = [w for w in normalized.split() if w and w.lower() not in _STOP_WORDS]
    if not words:
        # 全是停用词：用原始词但至少要有 3 个字符（排除纯 "LLC"/"Inc" 等）
        raw = [w for w in normalized.split() if len(w) >= 3]
        if not raw:
            return []
        words = raw[:2]

    core = "".join(words).lower()
    core = re.sub(r"[^a-z0-9]", "", core)[:30]
    # 排除纯停用词或过短结果（"llc"/"inc"/"co" 等不是有效域名核心）
    if len(core) < 4 or core in _STOP_WORDS:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(domain: str) -> None:
        if domain not in seen and len(candidates) < max_candidates:
            seen.add(domain)
            candidates.append(domain)

    # 模式 1：全词连写（最常见）
    for tld in _TLDS[:2]:
        _add(f"{core}.{tld}")

    # 模式 2：首词首字母 + 末词全词
    if len(words) >= 2:
        abbr = f"{words[0][0].lower()}{words[-1].lower()}"
        abbr = re.sub(r"[^a-z0-9]", "", abbr)[:25]
        if abbr and abbr != core:
            _add(f"{abbr}.com")

    # 模式 3：首词全词 + 末词首字母
    if len(words) >= 2:
        partial = f"{words[0].lower()}{words[-1][0].lower()}"
        partial = re.sub(r"[^a-z0-9]", "", partial)[:25]
        if partial and partial != core:
            _add(f"{partial}.com")

    # 模式 4：末词全词（如果末词有辨识度）
    if len(words) >= 2 and len(words[-1]) >= 4:
        last = re.sub(r"[^a-z0-9]", "", words[-1].lower())[:20]
        if last and last != core:
            _add(f"{last}.com")

    return candidates
