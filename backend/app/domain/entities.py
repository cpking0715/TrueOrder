"""领域实体：纯数据结构，不 import 任何框架。"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Audience = Literal["importer", "factory"]
BuyerType = Literal["importer", "factory", "both"]
Tier = Literal["potential", "precise", "excluded"]


@dataclass(frozen=True)
class HsAssignment:
    """产品 ↔ 税号对应关系。audience 指明这个税号面向哪类买家。"""

    hs_code: str  # 6 位 HS 税号
    audience: Audience
    note: str = ""


@dataclass(frozen=True)
class ProductConfig:
    """产品目录里一条产品的打分所需全部配置。"""

    product_id: int
    code: str
    name: str
    buyer_type: BuyerType
    hs_assignments: tuple[HsAssignment, ...] = ()
    buyer_keywords: tuple[str, ...] = ()  # 买家行业词：业务匹配用
    peer_keywords: tuple[str, ...] = ()  # 同行行业词：排除同行海外公司用
    description: str = ""


@dataclass(frozen=True)
class BillEvidence:
    """打分输入中的一条提单（已由基础设施层读出并归一化好国家）。"""

    bill_id: int
    arrival_date: date
    hs_code: str
    hs_suspect: bool
    origin_country: str  # 已归一化 ISO2，如 CN/VN
    shipper_name: str
    shipper_normalized: str
    product_description: str


@dataclass(frozen=True)
class CompanyFacts:
    """一家企业（规范化名称 + 国家识别）在某产品上下文里的全部事实。"""

    company_id: int
    normalized_name: str
    name_variants: tuple[str, ...]
    address: str
    country: str
    bills: tuple[BillEvidence, ...] = ()


@dataclass(frozen=True)
class ScoreReason:
    """一条可解释的得分/排除理由，bill_ids 保证能点回提单。"""

    code: str
    text: str
    bill_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ScoreResult:
    product_id: int
    company_id: int
    audience: Audience
    tier: Tier
    reasons: tuple[ScoreReason, ...] = ()
    exclusion_code: str | None = None
    # 供界面/导出直接展示的聚合（来自合格票）：
    shipments: int = 0
    last_arrival: date | None = None
    suppliers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BillLine:
    """提单 CSV 的一行（解析并校验后、入库前）。"""

    arrival_date: date
    consignee_name: str
    consignee_address: str
    shipper_name: str
    shipper_address: str
    hs_code: str
    product_description: str
    origin_country: str  # 原始值，入库前归一化
    consignee_country: str = ""  # 原始值，缺省按 US 处理
    shipper_country: str = ""  # 原始值，缺省跟原产国
    port: str = ""
    bill_number: str = ""
    quantity: str = ""


@dataclass(frozen=True)
class ProductRow:
    """产品目录 CSV 的一行（一个产品可拆多行，每行一个税号）。"""

    code: str
    name: str
    description: str
    buyer_type: BuyerType
    hs_code: str
    audience: Audience
    note: str = ""
    buyer_keywords: tuple[str, ...] = ()
    peer_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.buyer_type == "both" and self.audience not in ("importer", "factory"):
            raise ValueError("audience 必须是 importer 或 factory")


@dataclass
class ImportSummary:
    """一次 CSV 导入的结果统计。"""

    inserted_bills: int = 0
    duplicate_bills: int = 0
    suspect_hs_bills: int = 0
    invalid_rows: list[str] = field(default_factory=list)
    companies_created: int = 0
    companies_updated: int = 0
    products_upserted: int = 0
    hs_assignments_written: int = 0


@dataclass(frozen=True)
class FoundContact:
    """补全服务/官网抓取返回的一位联系人（写入 contacts 前的中转结构）。"""

    name: str | None = None
    title: str = ""
    email: str = ""
    phone: str | None = None
    source_ref: str = ""


@dataclass(frozen=True)
class FinderResult:
    """ContactFinder 一次查询的结果：域名候选 + 域名上的联系人。"""

    domain: str | None = None
    domain_company_name: str | None = None
    domain_country: str | None = None
    contacts: tuple[FoundContact, ...] = ()
