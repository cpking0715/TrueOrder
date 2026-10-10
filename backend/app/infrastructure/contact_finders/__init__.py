"""ContactFinder 适配器集：hunter（真实）/ fake（无 key 与测试）。

选择逻辑在 make_finder：有 TRUEORDER_HUNTER_API_KEY 用 Hunter，否则用 fake
（返回明显标注的演示数据，界面提示未配置）。
"""

from __future__ import annotations

from app.core.config import Settings
from app.domain.entities import FinderResult, FoundContact


class FakeContactFinder:
    """无 API Key 时的演示数据源：由公司名派生域名，产出明显标注的通用联系人。

    仅用于本地演示与测试——source_ref 一律带「fake」字样，可辨识可清除。
    """

    def find(self, domain: str, company_name: str, company_country: str = "") -> FinderResult:
        import re

        slug = re.sub(r"[^a-z0-9]+", "", (company_name or "company").lower())[:20]
        fake_domain = domain or (f"www.{slug}.com" if slug else None)
        contacts = (
            (
                FoundContact(
                    name=None,
                    title="",
                    email=f"sales@{fake_domain.removeprefix('www.')}",
                    source_ref="fake-finder（未配置 Hunter API Key 的演示数据）",
                ),
            )
            if fake_domain
            else ()
        )
        return FinderResult(
            domain=fake_domain,
            domain_company_name=company_name,
            # 回显公司国家：名称对齐时置信度达 high，演示路径与真实路径行为一致
            domain_country=company_country or None,
            contacts=contacts,
        )

    def verify(self, email: str) -> str:
        return "unknown"  # 演示数据不做可达性判断


class HunterContactFinder:
    """Hunter.io 适配器：Domain Search（按域名列邮箱）。网络错误向上抛，由任务队列退避。"""

    BASE = "https://api.hunter.io/v2"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _get(self, path: str, params: dict) -> dict:
        import httpx

        response = httpx.get(
            f"{self.BASE}/{path}",
            params={**params, "api_key": self._api_key},
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("data", {})

    def find(self, domain: str, company_name: str, company_country: str = "") -> FinderResult:
        # company_country 仅用于 fake 的置信度回显；Hunter 以接口返回为准
        data = self._get("domain-search", {"domain": domain, "company": company_name})
        found_domain = data.get("domain") or domain
        emails = data.get("emails") or []
        contacts = tuple(
            FoundContact(
                name=(
                    f"{(e.get('first_name') or '').strip()}"
                    f" {(e.get('last_name') or '').strip()}".strip()
                    or None
                ),
                title=(e.get("position") or "").strip(),
                email=(e.get("value") or "").strip(),
                phone=None,
                source_ref="hunter:domain-search",
            )
            for e in emails
            if (e.get("value") or "").strip()
        )
        return FinderResult(
            domain=found_domain,
            domain_company_name=(data.get("company") or "").strip() or None,
            domain_country=(data.get("country") or "").strip() or None,
            contacts=contacts,
        )

    def verify(self, email: str) -> str:
        data = self._get("email-verifier", {"email": email})
        status = (data.get("status") or "").lower()  # deliverable/undeliverable/risky/unknown
        if status in ("deliverable",):
            return "valid"
        if status in ("undeliverable",):
            return "invalid"
        return "unknown"


def make_finder(settings: Settings):
    """有 key 用 Hunter，否则 fake（演示数据 + 界面提示）。"""
    if settings.hunter_api_key:
        return HunterContactFinder(settings.hunter_api_key)
    return FakeContactFinder()
