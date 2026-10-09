"""CSV 行解析与去重指纹（纯函数）。"""

from datetime import date

import pytest

from app.domain.parse import (
    bill_dedup_hash,
    default_consignee_country,
    parse_bill_row,
    parse_product_rows,
)


def row(**kw):
    base = {
        "arrival_date": "2026-03-01",
        "consignee_name": "BROOKLYN APPAREL LLC",
        "consignee_address": "350 FIFTH AVE, NEW YORK NY 10118, USA",
        "shipper_name": "HANGZHOU GARMENT CO LTD",
        "shipper_address": "NO 66 INDUSTRIAL RD, HANGZHOU, CN",
        "origin_country": "CHINA",
        "hs_code": "620462",
        "product_description": "WOMENS COTTON TROUSERS",
        "port": "NEW YORK",
        "bill_number": "BOL-001",
        "quantity": "1200",
    }
    base.update(kw)
    return base


class Test提单行解析:
    def test_标准行解析成功(self):
        line, err = parse_bill_row(row(), "sample.csv", 2)
        assert err is None and line is not None
        assert line.arrival_date == date(2026, 3, 1)
        assert line.origin_country == "CHINA"

    @pytest.mark.parametrize("fmt", ["2026/03/01", "03/01/2026"])
    def test_兼容其他日期格式(self, fmt):
        line, err = parse_bill_row(row(arrival_date=fmt), "s.csv", 2)
        assert err is None and line.arrival_date == date(2026, 3, 1)

    def test_日期非法返回错误(self):
        line, err = parse_bill_row(row(arrival_date="2026-13-99"), "s.csv", 7)
        assert line is None and "第 7 行" in err

    def test_收发货人都为空返回错误(self):
        line, err = parse_bill_row(row(consignee_name="", shipper_name=""), "s.csv", 3)
        assert line is None and "均为空" in err

    def test_空收货人但发货人在_允许通过(self):
        line, err = parse_bill_row(row(consignee_name=""), "s.csv", 4)
        assert err is None and line.consignee_name == ""

    def test_表头带BOM与大小写不敏感(self):
        raw = {"﻿Arrival_Date": "2026-01-02", "CONSIGNEE_NAME": "X LLC"}
        line, err = parse_bill_row(raw, "s.csv", 2)
        assert err is None and line.consignee_name == "X LLC"


class Test去重指纹:
    def test_同票重复导入指纹一致(self):
        a, _ = parse_bill_row(row(), "a.csv", 2)
        b, _ = parse_bill_row(row(), "b.csv", 9)
        assert bill_dedup_hash(a) == bill_dedup_hash(b)

    def test_不同提单号指纹不同(self):
        a, _ = parse_bill_row(row(bill_number="BOL-001"), "a.csv", 2)
        b, _ = parse_bill_row(row(bill_number="BOL-002"), "a.csv", 3)
        assert bill_dedup_hash(a) != bill_dedup_hash(b)

    def test_名称大小写与法律后缀不影响指纹(self):
        a, _ = parse_bill_row(row(consignee_name="brooklyn apparel llc"), "a.csv", 2)
        b, _ = parse_bill_row(row(consignee_name="BROOKLYN APPAREL INC"), "a.csv", 3)
        assert bill_dedup_hash(a) == bill_dedup_hash(b)


class Test产品目录解析:
    @staticmethod
    def prod_rows():
        return [
            {
                "code": "P-GARMENT", "name": "成衣", "description": "卖给进口商",
                "buyer_type": "importer", "hs_code": "620462", "audience": "importer",
                "note": "成衣税号", "buyer_keywords": "APPAREL;CLOTHING",
                "peer_keywords": "GARMENT FACTORY",
            },
            {
                "code": "P-BOTH", "name": "面料", "description": "两者都卖",
                "buyer_type": "both", "hs_code": "600632", "audience": "factory",
                "buyer_keywords": "", "peer_keywords": "",
            },
            {
                "code": "P-BOTH", "name": "面料", "description": "两者都卖",
                "buyer_type": "both", "hs_code": "620462", "audience": "importer",
                "buyer_keywords": "", "peer_keywords": "",
            },
        ]

    def test_多行税号合并成一个产品(self):
        products, errors = parse_product_rows(Test产品目录解析.prod_rows(), "products.csv")
        assert errors == []
        assert len(products) == 2
        both = [p for p in products if p.code == "P-BOTH"][0]
        assert both.buyer_type == "both"
        assert {h.hs_code for h in both.hs_assignments} == {"600632", "620462"}

    def test_关键词按分号切分并大写(self):
        products, _ = parse_product_rows(
            [{"code": "A", "name": "n", "buyer_type": "importer", "hs_code": "620462",
              "audience": "importer", "buyer_keywords": "apparel; Clothing , box"}],
            "p.csv",
        )
        assert products[0].buyer_keywords == ("APPAREL", "CLOTHING", "BOX")

    def test_非法buyer_type报错(self):
        _, errors = parse_product_rows(
            [
                {
                    "code": "A", "name": "n", "buyer_type": "retailer",
                    "hs_code": "620462", "audience": "importer",
                }
            ],
            "p.csv",
        )
        assert errors and "buyer_type" in errors[0]


def test_默认收货人国家为US():
    assert default_consignee_country("") == "US"
    assert default_consignee_country("VIET NAM") == "VN"
