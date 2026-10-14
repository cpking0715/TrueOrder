"""Wikidata 免费目录源（HTTP 注入可测，不访问外网）。"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from app.domain.entities import FoundWebsite
from app.domain.normalize import normalize_company_name

API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "TrueOrder/1.0 (self-hosted buyer discovery; personal use)"
TIMEOUT = 10.0
MAX_CANDIDATES = 3

# 主要贸易国的 Wikidata Q-id → ISO2（覆盖不了的国家返回空，置信度判 medium）
COUNTRY_Q_MAP = {
    "Q30": "US", "Q148": "CN", "Q145": "GB", "Q142": "FR", "Q183": "DE",
    "Q17": "JP", "Q86": "KR", "Q38": "IT", "Q29": "ES", "Q55": "NL",
    "Q16": "CA", "Q96": "MX", "Q881": "VN", "Q869": "TH", "Q668": "IN",
    "Q408": "AU", "Q155": "BR", "Q43": "TR", "Q36": "PL", "Q34": "SE",
    "Q20": "NO", "Q35": "DK", "Q31": "BE", "Q40": "AT", "Q39": "CH",
    "Q334": "SG", "Q833": "MY", "Q252": "ID", "Q928": "PH", "Q843": "PK",
    "Q902": "BD", "Q79": "EG", "Q258": "ZA", "Q878": "AE", "Q854": "SA",
}


class WikidataDirectory:
    """按公司名在 Wikidata 找官网（P856），顺带国家（P17）与公开邮箱（P968）。

    只接受「规范化名称完全对齐」的实体（置信度判定的前提）；
    网络错误按未命中处理（None），不向上抛——目录源不可用不该烧计量额度以外的东西。
    """

    def __init__(self, fetch=None, polite_delay: float = 0.5) -> None:
        self._fetch = fetch or self._http_get
        self._delay = polite_delay

    def search(self, company_name: str, country: str) -> FoundWebsite | None:
        try:
            return self._search(company_name)
        except Exception:  # noqa: BLE001 - 目录源不可用按未命中处理，不向上抛
            return None

    def _search(self, company_name: str) -> FoundWebsite | None:
        normalized = normalize_company_name(company_name)
        if not normalized:
            return None
        data = self._fetch(
            API,
            {
                "action": "wbsearchentities",
                "search": company_name,
                "language": "en",
                "limit": "5",
                "type": "item",
                "format": "json",
            },
        )
        candidates = [
            item
            for item in (data or {}).get("search", [])
            if normalize_company_name(item.get("label", "")) == normalized
        ]
        for item in candidates[:MAX_CANDIDATES]:
            website = self._pick_canonical_website(self._claim_values(item["id"], "P856"))
            if not website:
                continue
            return FoundWebsite(
                website=website,
                matched_name=item.get("label", ""),
                country=self._entity_country(item["id"]),
                source="wikidata",
                email=self._claim_value(item["id"], "P968").removeprefix("mailto:"),
            )
        return None

    # ---------- 内部 ----------

    @staticmethod
    def _pick_canonical_website(urls: list[str]) -> str:
        """多值官网取最「主站」的一个：无路径 > 有路径；非区域前缀 > 区域前缀。"""
        from urllib.parse import urlparse

        # 国别顶级域（区域站信号）：com.cn / co.uk 之类
        cc_tlds = {
            "cn", "uk", "jp", "de", "fr", "at", "it", "es", "kr", "in",
            "au", "ca", "nl", "br", "mx", "vn", "th", "tr", "pl", "se",
        }

        def score(url: str) -> tuple:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            labels = host.split(".")
            regional = len(labels) > 2 and len(labels[0]) == 2 and labels[0] != "www"
            cctld = labels[-1] in cc_tlds
            has_path = parsed.path not in ("", "/")
            return (has_path, regional, cctld, len(labels))

        valid = [u for u in urls if u.startswith(("http://", "https://"))]
        if not valid:
            return ""
        return min(valid, key=score)

    def _claim_values(self, entity_id: str, property_id: str) -> list[str]:
        time.sleep(self._delay)
        data = self._fetch(
            API,
            {
                "action": "wbgetclaims",
                "entity": entity_id,
                "property": property_id,
                "format": "json",
            },
        )
        claims = (data or {}).get("claims", {}).get(property_id, [])
        values: list[str] = []
        for claim in claims:
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", "")
            if isinstance(value, dict):
                # 实体型 claim（如 P17 国家）：{"id": "Q30", "numeric-id": 30}
                value = value.get("id") or (
                    f"Q{value.get('numeric-id')}" if value.get("numeric-id") else ""
                )
            value = str(value or "")
            if value and value not in values:
                values.append(value)
        return values

    def _claim_value(self, entity_id: str, property_id: str) -> str:
        values = self._claim_values(entity_id, property_id)
        return values[0] if values else ""

    def _entity_country(self, entity_id: str) -> str:
        qid = self._claim_value(entity_id, "P17")
        return COUNTRY_Q_MAP.get(qid, "")

    def _http_get(self, url: str, params: dict) -> dict:
        if not url.startswith("https://"):
            raise ValueError(f"只允许 https 目录接口：{url}")
        full = f"{url}?{urllib.parse.urlencode(params)}"
        # 上一行已限定 https 方案（URL 来自代码常量），排除 file:/自定义方案
        request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
