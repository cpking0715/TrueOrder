"""CSV 导出安全：公式注入转义。

单元格以 = + - @ 或制表符/回车/换行开头时加单引号前缀，防止 Excel 打开时执行公式。
"""

from __future__ import annotations

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def sanitize_csv_cell(value) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_DANGEROUS_PREFIXES):
        return "'" + text
    return text
