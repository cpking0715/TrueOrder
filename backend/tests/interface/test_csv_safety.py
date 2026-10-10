"""CSV 导出安全：公式注入转义（= + - @ 与制表/换行开头的单元格加 ' 前缀）。"""

from __future__ import annotations

from app.interface.csv_safety import sanitize_csv_cell


class Test公式注入转义:
    def test_等号开头加前缀(self):
        assert sanitize_csv_cell('=HYPERLINK("http://e","x")') == '\'=HYPERLINK("http://e","x")'

    def test_危险前缀都转义(self):
        for v in ["+SUM(A1)", "-1+1", "@cmd", "\t=1", "\r=1", "\n=1"]:
            assert sanitize_csv_cell(v).startswith("'"), v

    def test_正常值不变(self):
        assert sanitize_csv_cell("BROOKLYN APPAREL LLC") == "BROOKLYN APPAREL LLC"
        assert sanitize_csv_cell("普通公司") == "普通公司"
        assert sanitize_csv_cell("A-B 正常连字符") == "A-B 正常连字符"

    def test_空与非字符串安全(self):
        assert sanitize_csv_cell("") == ""
        assert sanitize_csv_cell(None) == ""
        assert sanitize_csv_cell(123) == "123"
