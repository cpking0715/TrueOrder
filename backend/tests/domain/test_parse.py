"""CSV 行解析与去重指纹（纯函数）。"""

from datetime import date

import pytest

from app.domain.parse import (
    bill_dedup_hash,
    build_quick_product,
    default_consignee_country,
    parse_bill_row,
    parse_product_rows,
    suggest_buyer_keywords,
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

    def test_同日同当事人同税号不同数量指纹不同(self):
        # F3 回归：拼柜/分单场景，靠数量区分
        a, _ = parse_bill_row(row(quantity="1200", bill_number=""), "a.csv", 2)
        b, _ = parse_bill_row(row(quantity="900", bill_number=""), "a.csv", 3)
        assert bill_dedup_hash(a) != bill_dedup_hash(b)

    def test_同日同当事人同税号不同港口指纹不同(self):
        a, _ = parse_bill_row(row(port="NEW YORK", bill_number=""), "a.csv", 2)
        b, _ = parse_bill_row(row(port="SAVANNAH", bill_number=""), "a.csv", 3)
        assert bill_dedup_hash(a) != bill_dedup_hash(b)

    def test_原产国不同指纹不同(self):
        a, _ = parse_bill_row(row(origin_country="CHINA", bill_number=""), "a.csv", 2)
        b, _ = parse_bill_row(row(origin_country="VIETNAM", bill_number=""), "a.csv", 3)
        assert bill_dedup_hash(a) != bill_dedup_hash(b)

    def test_描述差异超出八十字符仍影响指纹(self):
        # F3 回归：描述截断会让长描述的后段差异丢失
        long_a = "W" * 100 + "A"
        long_b = "W" * 100 + "B"
        a, _ = parse_bill_row(row(product_description=long_a, bill_number=""), "a.csv", 2)
        b, _ = parse_bill_row(row(product_description=long_b, bill_number=""), "a.csv", 3)
        assert bill_dedup_hash(a) != bill_dedup_hash(b)


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

    def test_多行产品的关键词合并而不是取首行(self):
        # F5 连带：both 产品两类受众各有买家词，合并后都要保留
        products, _ = parse_product_rows(
            [
                {"code": "B", "name": "n", "buyer_type": "both",
                 "hs_code": "620462", "audience": "importer", "buyer_keywords": "APPAREL"},
                {"code": "B", "name": "n", "buyer_type": "both",
                 "hs_code": "600632", "audience": "factory", "buyer_keywords": "WEAVING"},
            ],
            "p.csv",
        )
        assert products[0].buyer_keywords == ("APPAREL", "WEAVING")

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


class Test快速建产品:
    """「我填我的产品，帮我找客户」表单提交 → ProductConfig。"""

    def test_importer产品单税号单受众且带默认买家词(self):
        product, error = build_quick_product(
            code="QUICK-0001", name="女士棉质长裤", hs_code="620462", buyer_type="importer"
        )
        assert error is None
        assert product is not None
        assert product.buyer_type == "importer"
        assert [(h.hs_code, h.audience) for h in product.hs_assignments] == [("620462", "importer")]
        assert product.buyer_keywords  # 未填买家词时给受众默认词，业务匹配不缺席
        assert product.peer_keywords == ()

    def test_both产品同税号拆两类受众(self):
        product, _ = build_quick_product(
            code="QUICK-0002", name="面料", hs_code="600632", buyer_type="both"
        )
        assert product is not None
        assert sorted(h.audience for h in product.hs_assignments) == ["factory", "importer"]

    def test_显式关键词覆盖默认且归一化去重(self):
        product, _ = build_quick_product(
            code="QUICK-0003",
            name="成衣",
            hs_code="620462",
            buyer_type="importer",
            buyer_keywords=["apparel", "APPAREL", " wholesale "],
            peer_keywords=["garment factory"],
        )
        assert product is not None
        assert product.buyer_keywords == ("APPAREL", "WHOLESALE")
        assert product.peer_keywords == ("GARMENT FACTORY",)

    def test_默认买家词按受众区分且both取并集(self):
        importer_kw = suggest_buyer_keywords("importer")
        factory_kw = suggest_buyer_keywords("factory")
        assert importer_kw and factory_kw
        assert not set(importer_kw) & set(factory_kw)
        assert set(suggest_buyer_keywords("both")) == set(importer_kw) | set(factory_kw)

    def test_名称缺失报错(self):
        product, error = build_quick_product(
            code="QUICK-0004", name="  ", hs_code="620462", buyer_type="importer"
        )
        assert product is None
        assert error and "名称" in error

    def test_税号非法报错(self):
        product, error = build_quick_product(
            code="QUICK-0005", name="成衣", hs_code="62x462", buyer_type="importer"
        )
        assert product is None
        assert error and "税号" in error

    def test_非法buyer_type报错(self):
        product, error = build_quick_product(
            code="QUICK-0006", name="成衣", hs_code="620462", buyer_type="retailer"
        )
        assert product is None
        assert error and "buyer_type" in error
