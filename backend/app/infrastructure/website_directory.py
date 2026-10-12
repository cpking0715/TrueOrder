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
            website = self._claim_value(item["id"], "P856")
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

    def _claim_value(self, entity_id: str, property_id: str) -> str:
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
        if not claims:
            return ""
        datavalue = claims[0].get("mainsnak", {}).get("datavalue", {})
        value = datavalue.get("value", "")
        return str(value) if value else ""

    def _entity_country(self, entity_id: str) -> str:
        qid = self._claim_value(entity_id, "P17")
        return COUNTRY_Q_MAP.get(qid, "")

    def _http_get(self, url: str, params: dict) -> dict:
        full = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
