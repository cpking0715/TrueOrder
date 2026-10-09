"""领域层定义的端口：基础设施只做实现，可整体替换。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.entities import CompanyFacts, ProductConfig, ScoreResult


class ProductReader(Protocol):
    def list_products(self) -> list[ProductConfig]: ...

    def get_product(self, product_id: int) -> ProductConfig | None: ...


class BuyerPoolReader(Protocol):
    """按税号族（4 位前缀）装载候选企业及其全部相关提单事实。"""

    def load_pool(self, family_prefixes: Sequence[str]) -> list[CompanyFacts]: ...


class ScoreWriter(Protocol):
    def replace_scores(self, product_id: int, results: Sequence[ScoreResult]) -> int: ...


class ProductImportSink(Protocol):
    def upsert_product(self, product: ProductConfig) -> int: ...


class BillImportSink(Protocol):
    def insert_bill(self, line, source_ref: str, row_no: int) -> str: ...
    # 返回 'inserted' | 'duplicate'


class CompanyImportSink(Protocol):
    def upsert_company(self, raw_name: str, address: str, country: str) -> int: ...
