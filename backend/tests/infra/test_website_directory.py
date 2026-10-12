"""Wikidata 目录源：解析、名称对齐、国家映射、错误吞并（HTTP 全注入，零外网）。"""

from __future__ import annotations

import pytest

from app.infrastructure.website_directory import WikidataDirectory


class FakeHttp:
    """按 (action, entity) 预置响应；未预置的请求抛网络错。"""

    def __init__(self, responses: dict, fail_keys: set | None = None) -> None:
        self.responses = responses
        self.fail_keys = fail_keys or set()
        self.calls: list[str] = []

    def __call__(self, url: str, params: dict) -> dict:
        if params.get("entity"):
            key = f"{params['action']}:{params['entity']}|{params.get('property', '')}"
        else:
            key = f"{params['action']}:{params.get('search')}"
        self.calls.append(key)
        if key in self.fail_keys:
            raise OSError("network down")
        return self.responses[key]


def search_response(label: str, entity_id: str = "Q123") -> dict:
    return {"search": [{"id": entity_id, "label": label}]}


def claims_response(property_id: str, value) -> dict:
    return {"claims": {property_id: [{"mainsnak": {"datavalue": {"value": value}}}]}}


@pytest.fixture()
def no_delay():
    return WikidataDirectory(fetch=FakeHttp({}), polite_delay=0)


def make_dir(responses: dict, fail_keys: set | None = None) -> tuple[WikidataDirectory, FakeHttp]:
    http = FakeHttp(responses, fail_keys)
    return WikidataDirectory(fetch=http, polite_delay=0), http


class Test搜索:
    def test_命中官网国家与邮箱(self):
        directory, _ = make_dir({
            "wbsearchentities:Brooklyn Apparel LLC": search_response("Brooklyn Apparel", "Q1"),
            "wbgetclaims:Q1|P856": claims_response("P856", "https://brooklynapparel.com"),
            "wbgetclaims:Q1|P17": claims_response("P17", "Q30"),
            "wbgetclaims:Q1|P968": claims_response("P968", "mailto:info@brooklynapparel.com"),
        })
        found = directory.search("Brooklyn Apparel LLC", "US")
        assert found is not None
        assert found.website == "https://brooklynapparel.com"
        assert found.matched_name == "Brooklyn Apparel"
        assert found.country == "US"
        assert found.source == "wikidata"
        assert found.email == "info@brooklynapparel.com"

    def test_名称不对齐的实体被跳过(self):
        directory, _ = make_dir({
            "wbsearchentities:Brooklyn Apparel LLC": search_response(
                "Brooklyn Apparel Group", "Q1"
            ),
        })
        assert directory.search("Brooklyn Apparel LLC", "US") is None

    def test_对齐但无官网继续找下一个候选(self):
        directory, _ = make_dir({
            "wbsearchentities:Brooklyn Apparel LLC": {
                "search": [
                    {"id": "Q1", "label": "Brooklyn Apparel"},
                    {"id": "Q2", "label": "Brooklyn Apparel"},
                ]
            },
            "wbgetclaims:Q1|P856": {"claims": {}},
            "wbgetclaims:Q2|P856": claims_response("P856", "https://ba.com"),
            "wbgetclaims:Q2|P17": claims_response("P17", "Q30"),
            "wbgetclaims:Q2|P968": {"claims": {}},
        })
        found = directory.search("Brooklyn Apparel LLC", "US")
        assert found is not None
        assert found.website == "https://ba.com"

    def test_未知国家返回空串(self):
        directory, _ = make_dir({
            "wbsearchentities:Brooklyn Apparel LLC": search_response("Brooklyn Apparel", "Q9"),
            "wbgetclaims:Q9|P856": claims_response("P856", "https://x.com"),
            "wbgetclaims:Q9|P17": claims_response("P17", "Q99999"),
            "wbgetclaims:Q9|P968": {"claims": {}},
        })
        found = directory.search("Brooklyn Apparel LLC", "US")
        assert found is not None
        assert found.country == ""


class Test容错:
    def test_搜索接口异常按未命中处理(self):
        directory, _ = make_dir({}, fail_keys={"wbsearchentities:Brooklyn Apparel LLC"})
        assert directory.search("Brooklyn Apparel LLC", "US") is None

    def test_空公司名不请求(self):
        directory, http = make_dir({})
        assert directory.search("", "US") is None
        assert http.calls == []
