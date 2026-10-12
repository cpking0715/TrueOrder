"""领域层定义的端口：基础设施只做实现，可整体替换。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.domain.entities import (
    CompanyFacts,
    FinderResult,
    FoundContact,
    FoundWebsite,
    ProductConfig,
    ScoreResult,
)


class ProductReader(Protocol):
    def list_products(self) -> list[ProductConfig]: ...

    def get_product(self, product_id: int) -> ProductConfig | None: ...


class BuyerPoolReader(Protocol):
    """按税号族（4 位前缀）装载候选企业及其窗内提单事实（as_of 往前 24 个月）。"""

    def load_pool(
        self, family_prefixes: Sequence[str], as_of: date
    ) -> list[CompanyFacts]: ...


class ScoreWriter(Protocol):
    def replace_scores(self, product_id: int, results: Sequence[ScoreResult]) -> int: ...


class ProductImportSink(Protocol):
    def upsert_product(self, product: ProductConfig) -> int: ...


class BillImportSink(Protocol):
    def insert_bill(self, line, source_ref: str, row_no: int) -> str: ...
    # 返回 'inserted' | 'duplicate'


class CompanyImportSink(Protocol):
    def upsert_company(self, raw_name: str, address: str, country: str) -> int: ...


class ContactFinder(Protocol):
    """按次联系人补全端口（hunter/fake 适配器可整体替换）。"""

    def find(
        self, domain: str, company_name: str, company_country: str = ""
    ) -> FinderResult: ...

    def verify(self, email: str) -> str:
        """返回 valid | invalid | unknown（不可判定时 unknown）。"""


class WebsiteDirectory(Protocol):
    """免费官网目录源：按公司名找官网域名，零额度、结果带来源可审计。"""

    def search(
        self, company_name: str, country: str
    ) -> FoundWebsite | None: ...


class PageContactExtractor(Protocol):
    """AI 页面联系人提取端口：从页面文本抽结构化联系人，失败由调用方兜底。"""

    def extract(
        self, page_text: str, url: str
    ) -> list[FoundContact]: ...
