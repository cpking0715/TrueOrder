"""极简 PDF 生成（纯标准库，零新依赖）：单页、Helvetica、逐行文本。

选型理由：仓库现无 PDF 依赖；PI/报价单只需英文文字表格，引入 reportlab/fpdf2
（连带 Pillow 等）不划算。非 Latin-1 字符替换为 '?'（PI 面向海外买家，内容为英文）。
"""

from __future__ import annotations

_PAGE_W, _PAGE_H = 595, 842  # A4（pt）
_LEFT, _TOP, _LEADING = 50, 790, 16
_MAX_LINES = 46


def _escape(text: str) -> str:
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_text_pdf(lines: list[tuple[str, int]]) -> bytes:
    """lines：[(文本, 字号)]；超出单页的行截断（v0.1 报价单远小于一页）。"""
    ops = ["BT", f"{_LEFT} {_TOP} Td"]
    for i, (text, size) in enumerate(lines[:_MAX_LINES]):
        if i:
            ops.append(f"0 -{_LEADING} Td")
        ops.append(f"/F1 {size} Tf ({_escape(text)}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_W} {_PAGE_H}] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ).encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)
