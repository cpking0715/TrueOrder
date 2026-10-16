"""PI（形式发票）排版：询盘行 → 文本行 → 极简 PDF。只排版，不涉及收款。"""

from __future__ import annotations

from datetime import date

from app.domain.kit_sales import QuoteLine, line_total, pi_number
from app.infrastructure.kit_sales_repository import InquiryRow
from app.infrastructure.pdf_writer import render_text_pdf


def build_pi_pdf(
    row: InquiryRow, country: str, seller: str, seller_address: str, issued_on: date
) -> tuple[bytes, str]:
    number = pi_number(row.id, issued_on)
    total = line_total(QuoteLine(row.product_name, row.quantity, row.unit_price))
    lines: list[tuple[str, int]] = [
        ("PROFORMA INVOICE", 18),
        (f"No.: {number}    Date: {issued_on.isoformat()}", 10),
        ("", 10),
        (f"Seller: {seller or '(set TRUEORDER_SMTP_FROM_NAME)'}", 10),
        (f"Address: {seller_address or '(set TRUEORDER_COMPANY_ADDRESS)'}", 10),
        (f"Buyer: {row.company_name} ({country})", 10),
        ("", 10),
        ("Item | Qty | Unit price | Amount", 11),
        (
            f"{row.product_name} | {row.quantity} | {row.currency} {row.unit_price:.2f} | "
            f"{row.currency} {total}",
            10,
        ),
        ("", 10),
        (f"TOTAL: {row.currency} {total}", 12),
        ("", 10),
        ("Validity: 30 days. Payment & shipping terms to be confirmed in contract.", 9),
        ("This PI is a quotation document and not a demand for payment.", 9),
    ]
    return render_text_pdf(lines), number
