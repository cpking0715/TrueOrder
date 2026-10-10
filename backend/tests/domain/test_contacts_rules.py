"""WP4 领域规则：域名置信度、收件人排序、邮箱/电话抽取、抓取页选择（纯函数）。"""

from __future__ import annotations

from app.domain.contacts import (
    RecipientCandidate,
    extract_emails,
    extract_phones,
    pick_best_recipient,
    select_crawl_pages,
    website_confidence,
)


class Test域名置信度:
    def test_公司名与国家都一致为high(self):
        assert (
            website_confidence("Brooklyn Apparel LLC", "BROOKLYN APPAREL", "US", "US")
            == "high"
        )

    def test_公司名一致国家不一致为medium(self):
        assert (
            website_confidence("Brooklyn Apparel LLC", "BROOKLYN APPAREL", "DE", "US")
            == "medium"
        )

    def test_公司名不一致为low(self):
        assert website_confidence("Other Corp", "BROOKLYN APPAREL", "US", "US") == "low"

    def test_无公司名为low(self):
        assert website_confidence("", "BROOKLYN APPAREL", "US", "US") == "low"


class Test收件人排序:
    def test_具名且valid最优(self):
        candidates = [
            RecipientCandidate(1, None, "Purchasing Manager", "valid", True),
            RecipientCandidate(2, "John", "CEO", "valid", False),
        ]
        assert pick_best_recipient(candidates).contact_id == 2

    def test_具名unknown优于通用邮箱(self):
        candidates = [
            RecipientCandidate(1, None, "", "valid", True),
            RecipientCandidate(2, "Mary", "Sales", "unknown", False),
        ]
        assert pick_best_recipient(candidates).contact_id == 2

    def test_同级职位关键词优先(self):
        candidates = [
            RecipientCandidate(1, "Ann", "Marketing Director", "valid", False),
            RecipientCandidate(2, "Bob", "Procurement Lead", "valid", False),
        ]
        assert pick_best_recipient(candidates).contact_id == 2

    def test_同级无关键词按id稳定(self):
        candidates = [
            RecipientCandidate(5, "Ann", "CEO", "valid", False),
            RecipientCandidate(3, "Bob", "CTO", "valid", False),
        ]
        assert pick_best_recipient(candidates).contact_id == 3

    def test_空列表返回None(self):
        assert pick_best_recipient([]) is None


class Test邮箱抽取:
    def test_从文本抽邮箱去重保序(self):
        text = "联系 sales@example.com 或 John Smith <john@example.com>；sales@example.com 重复"
        assert extract_emails(text) == ["sales@example.com", "john@example.com"]

    def test_尾部标点剥离(self):
        assert extract_emails("write to info@example.com.") == ["info@example.com"]

    def test_无邮箱返回空(self):
        assert extract_emails("no contact here") == []


class Test电话抽取:
    def test_国际格式电话(self):
        text = "Tel: +1 415 555 1234 / +86-755-1234-5678"
        phones = extract_phones(text)
        assert any("415" in p for p in phones)
        assert any("755" in p for p in phones)


BASE = "https://www.example.com/"


class Test抓取页选择:
    def test_首页加contact_about_team链接(self):
        hrefs = ["/about-us", "/products", "contact.html", "/team", "https://other.com/contact"]
        selected = select_crawl_pages(BASE, hrefs)
        assert selected[0] == BASE
        assert "https://www.example.com/about-us" in selected
        assert "https://www.example.com/contact.html" in selected
        assert "https://www.example.com/team" in selected
        assert all("other.com" not in u for u in selected)  # 跨域不抓

    def test_总页数封顶5(self):
        hrefs = [f"/contact{i}" for i in range(10)]
        assert len(select_crawl_pages(BASE, hrefs)) == 5

    def test_去重与相对路径解析(self):
        selected = select_crawl_pages(BASE, ["/about", "/about", "about"])
        assert selected.count("https://www.example.com/about") == 1
