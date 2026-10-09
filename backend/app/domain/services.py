"""应用服务：编排端口与领域规则（导入触发重打分）。只依赖领域与端口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.entities import ProductConfig, ScoreResult
from app.domain.normalize import hs_family_prefix
from app.domain.ports import BuyerPoolReader, ProductReader, ScoreWriter
from app.domain.scoring import score_company


@dataclass(frozen=True)
class RescoreSummary:
    product_code: str
    audiences: tuple[str, ...]
    potential: int
    precise: int
    excluded: int


class RescoreService:
    """对全部（或单个）产品重算潜在/精准/排除结果。"""

    def __init__(self, products: ProductReader, pool: BuyerPoolReader, scores: ScoreWriter):
        self._products = products
        self._pool = pool
        self._scores = scores

    def rescore_all(self, as_of: date) -> list[RescoreSummary]:
        return [self._rescore_one(p, as_of) for p in self._products.list_products()]

    def rescore_product(self, product_id: int, as_of: date) -> RescoreSummary | None:
        product = self._products.get_product(product_id)
        if product is None:
            return None
        return self._rescore_one(product, as_of)

    def _rescore_one(self, product: ProductConfig, as_of: date) -> RescoreSummary:
        audiences = sorted({a.audience for a in product.hs_assignments})
        families = sorted({hs_family_prefix(a.hs_code) for a in product.hs_assignments})
        pool = self._pool.load_pool(families)
        results: list[ScoreResult] = []
        for audience in audiences:
            for facts in pool:
                result = score_company(product, audience, facts, as_of)
                if result is not None:
                    results.append(result)
        self._scores.replace_scores(product.product_id, results)
        return RescoreSummary(
            product_code=product.code,
            audiences=tuple(audiences),
            potential=sum(1 for r in results if r.tier == "potential"),
            precise=sum(1 for r in results if r.tier == "precise"),
            excluded=sum(1 for r in results if r.tier == "excluded"),
        )
