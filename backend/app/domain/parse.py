"""CSV 行 → 领域对象的解析与校验（纯函数，无 I/O）。

文件读写属于基础设施；这里只负责一行数据怎么变成合法的领域对象。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.domain.entities import Audience, BillLine, BuyerType, HsAssignment, ProductConfig
from app.domain.normalize import is_valid_hs, normalize_company_name, normalize_country

BILL_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y")

_BUYER_TYPES: tuple[BuyerType, ...] = ("importer", "factory", "both")
_AUDIENCES: tuple[Audience, ...] = ("importer", "factory")


def _cell(row: Mapping[str, Any], *names: str) -> str:
    """按候选列名取值（去 BOM/空白），缺失返回空串。"""
    for name in names:
        for key, value in row.items():
            if key is None:
                continue
            if key.strip().lstrip("﻿").lower() == name:
                return (value or "").strip()
    return ""


def parse_bill_row(
    row: Mapping[str, Any], source: str, line_no: int
) -> tuple[BillLine | None, str | None]:
    """解析提单一行。返回 (BillLine, None) 或 (None, 错误描述)。"""
    raw_date = _cell(row, "arrival_date", "date", "arrival")
    arrival = None
    for fmt in BILL_DATE_FORMATS:
        try:
            arrival = datetime.strptime(raw_date, fmt).date()
            break
        except ValueError:
            continue
    if arrival is None:
        return None, f"{source} 第 {line_no} 行：到港日期无法解析（{raw_date!r}）"

    line = BillLine(
        arrival_date=arrival,
        consignee_name=_cell(row, "consignee_name", "consignee"),
        consignee_address=_cell(row, "consignee_address"),
        shipper_name=_cell(row, "shipper_name", "shipper"),
        shipper_address=_cell(row, "shipper_address"),
        hs_code=_cell(row, "hs_code", "hs"),
        product_description=_cell(row, "product_description", "description", "goods"),
        origin_country=_cell(row, "origin_country", "country_of_origin", "origin"),
        consignee_country=_cell(row, "consignee_country"),
        shipper_country=_cell(row, "shipper_country"),
        port=_cell(row, "port", "port_of_unlading"),
        bill_number=_cell(row, "bill_number", "bill_no", "bol"),
        quantity=_cell(row, "quantity", "qty"),
    )
    if not line.consignee_name and not line.shipper_name:
        return None, f"{source} 第 {line_no} 行：收货人与发货人均为空"
    return line, None


def bill_dedup_hash(line: BillLine) -> str:
    """同一票重复导入的去重指纹：业务字段拼接后取 MD5。

    原产国/港口/数量参与指纹，避免「同日同当事人同税号」的拼柜/分单被误合并；
    货物描述完整参与（不截断），法律后缀已随名称归一化折叠。
    """
    payload = "|".join(
        (
            line.arrival_date.isoformat(),
            normalize_company_name(line.consignee_name),
            normalize_company_name(line.shipper_name),
            (line.hs_code or "").strip(),
            (line.bill_number or "").strip().upper(),
            _squash_desc(line.product_description),
            normalize_country(line.origin_country),
            _squash_desc(line.port),
            _squash_desc(line.quantity),
        )
    )
    return hashlib.md5(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


def _squash_desc(text: str) -> str:
    return " ".join((text or "").upper().split())


def parse_product_rows(
    rows: Sequence[Mapping[str, Any]], source: str
) -> tuple[list[ProductConfig], list[str]]:
    """产品目录多行（一个产品可多行税号）→ ProductConfig 列表（product_id 未定，置 0）。"""
    errors: list[str] = []
    grouped: dict[str, dict[str, Any]] = {}
    for line_no, row in enumerate(rows, start=2):  # 第 1 行是表头
        code = _cell(row, "code", "product_code")
        name = _cell(row, "name", "product_name")
        buyer_type = _cell(row, "buyer_type", "sell_to").lower()
        hs_code = _cell(row, "hs_code", "hs")
        audience = _cell(row, "audience").lower() or buyer_type
        if buyer_type not in _BUYER_TYPES:
            errors.append(
                f"{source} 第 {line_no} 行：buyer_type 必须是 importer/factory/both，"
                f"得到 {buyer_type!r}"
            )
            continue
        if audience not in _AUDIENCES:
            errors.append(
                f"{source} 第 {line_no} 行：audience 必须是 importer/factory，得到 {audience!r}"
            )
            continue
        if not code or not name or not hs_code:
            errors.append(f"{source} 第 {line_no} 行：code/name/hs_code 缺失")
            continue

        entry = grouped.setdefault(
            code,
            {
                "code": code,
                "name": name,
                "description": _cell(row, "description"),
                "buyer_type": buyer_type,
                "hs_rows": [],
                "buyer_keywords": [],
                "peer_keywords": [],
                "first_line": line_no,
            },
        )
        # both 产品多行（每受众一行）时，关键词跨行合并去重，不能只取首行
        _merge_keywords(entry["buyer_keywords"], _cell(row, "buyer_keywords"))
        _merge_keywords(entry["peer_keywords"], _cell(row, "peer_keywords"))
        entry["hs_rows"].append(
            {
                "hs_code": hs_code,
                "audience": audience,
                "note": _cell(row, "note"),
            }
        )

    products: list[ProductConfig] = []
    for code, entry in grouped.items():
        hs = tuple(
            HsAssignment(hs_code=r["hs_code"], audience=r["audience"], note=r["note"])
            for r in entry["hs_rows"]
        )
        products.append(
            ProductConfig(
                product_id=0,
                code=code,
                name=entry["name"],
                buyer_type=entry["buyer_type"],
                hs_assignments=hs,
                buyer_keywords=tuple(entry["buyer_keywords"]),
                peer_keywords=tuple(entry["peer_keywords"]),
                description=entry["description"],
            )
        )
    return products, errors


def _split_keywords(cell: str) -> list[str]:
    return [kw.strip().upper() for kw in (cell or "").replace(",", ";").split(";") if kw.strip()]


def _merge_keywords(target: list[str], cell: str) -> None:
    for keyword in _split_keywords(cell):
        if keyword not in target:
            target.append(keyword)


# 快速建产品未填买家词时的受众默认词（子串匹配用，前缀式写法可覆盖多后缀）
_DEFAULT_BUYER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "importer": ("IMPORT", "TRADING", "WHOLESALE", "DISTRIBUT"),
    "factory": ("MANUFACTUR", "MILL", "FACTORY", "INDUSTRIES"),
}


def suggest_buyer_keywords(buyer_type: BuyerType) -> tuple[str, ...]:
    """按受众给默认买家行业词；both 取两类并集。"""
    if buyer_type == "both":
        merged = (*_DEFAULT_BUYER_KEYWORDS["importer"], *_DEFAULT_BUYER_KEYWORDS["factory"])
        return tuple(dict.fromkeys(merged))
    return _DEFAULT_BUYER_KEYWORDS.get(buyer_type, ())


def build_quick_product(
    *,
    code: str,
    name: str,
    hs_code: str,
    buyer_type: str,
    description: str = "",
    buyer_keywords: Sequence[str] = (),
    peer_keywords: Sequence[str] = (),
) -> tuple[ProductConfig | None, str | None]:
    """「填产品找客户」表单 → ProductConfig。校验失败返回 (None, 错误描述)。

    买家词未填时用受众默认词兜底（业务匹配不缺席）；同行词无默认（需懂行的人配）。
    """
    name = name.strip()
    if not name:
        return None, "产品名称必填"
    hs = (hs_code or "").strip()
    if not is_valid_hs(hs):
        return None, f"税号非法：{hs!r}（需 6-10 位数字，不能全零）"
    if buyer_type not in _BUYER_TYPES:
        return None, f"buyer_type 必须是 importer/factory/both，得到 {buyer_type!r}"

    audiences: tuple[Audience, ...] = (
        ("importer", "factory") if buyer_type == "both" else (buyer_type,)
    )
    user_buyer = tuple(dict.fromkeys(kw.strip().upper() for kw in buyer_keywords if kw.strip()))
    user_peer = tuple(dict.fromkeys(kw.strip().upper() for kw in peer_keywords if kw.strip()))
    config = ProductConfig(
        product_id=0,
        code=code,
        name=name,
        buyer_type=buyer_type,
        hs_assignments=tuple(HsAssignment(hs_code=hs, audience=a) for a in audiences),
        buyer_keywords=user_buyer or suggest_buyer_keywords(buyer_type),
        peer_keywords=user_peer,
        description=(description or "").strip(),
    )
    return config, None


def default_consignee_country(raw: str) -> str:
    return normalize_country(raw) if raw else "US"
