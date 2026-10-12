"""官网抓取器（本地 HTTP 夹具，不访问外网；robots/SSRF/超大页/抽取全约束）。"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.infrastructure.crawler import CrawlBlocked, WebsiteCrawler


class FixtureSite(BaseHTTPRequestHandler):
    """按路径返回预置页面；/robots-disallow 站点用独立实例。"""

    pages: dict[str, str] = {}
    redirects: dict[str, str] = {}

    def do_GET(self):  # noqa: N802 - http.server 约定
        if self.path in self.redirects:
            self.send_response(302)
            self.send_header("Location", self.redirects[self.path])
            self.end_headers()
            return
        body = self.pages.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # 静音测试日志
        pass


@pytest.fixture()
def make_site():
    servers: list[ThreadingHTTPServer] = []

    def _make(pages: dict[str, str], redirects: dict[str, str] | None = None) -> str:
        FixtureSite.pages = pages
        FixtureSite.redirects = redirects or {}
        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureSite)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        host, port = server.server_address[:2]
        return f"http://127.0.0.1:{port}"

    yield _make
    for s in servers:
        s.shutdown()


def crawler() -> WebsiteCrawler:
    return WebsiteCrawler(allow_loopback=True)  # 仅测试夹具放行回环；生产默认拒绝


class Test抓取与抽取:
    def test_首页与联系页邮箱抽取带来源URL(self, make_site):
        base = make_site({
            "/": '<a href="/contact-us">Contact</a> reach us at sales@example.com',
            "/contact-us": "John: john@example.com | Tel: +1 415 555 1234",
        })
        result = crawler().crawl(f"{base}/")
        assert set(result.pages_fetched) == {f"{base}/", f"{base}/contact-us"}
        emails = {c.email for c in result.contacts}
        assert emails == {"sales@example.com", "john@example.com"}
        by_email = {c.email: c.source_ref for c in result.contacts}
        assert by_email["sales@example.com"] == f"website:{base}/"
        assert by_email["john@example.com"] == f"website:{base}/contact-us"

    def test_无关链接不抓(self, make_site):
        base = make_site({
            "/": '<a href="/blog/post-1">blog</a>',
            "/blog/post-1": "blog@example.com",
        })
        result = crawler().crawl(f"{base}/")
        assert result.pages_fetched == [f"{base}/"]
        assert result.contacts == []

    def test_robots禁止整站(self, make_site):
        base = make_site({
            "/robots.txt": "User-agent: *\nDisallow: /",
            "/": "hi@example.com",
        })
        with pytest.raises(CrawlBlocked, match="robots"):
            crawler().crawl(f"{base}/")

    def test_重定向到链路本地地址被拒(self, make_site):
        base = make_site({}, redirects={"/": "http://169.254.169.254/latest"})
        with pytest.raises(CrawlBlocked, match="内网|保留"):
            crawler().crawl(f"{base}/")

    def test_超大页面放弃(self, make_site):
        base = make_site({"/": "x" * (1024 * 1024 + 10)})
        result = crawler().crawl(f"{base}/")
        assert result.pages_fetched == []
        assert "首页抓取失败" in result.blocked_reason

    def test_同站重定向可跟随(self, make_site):
        base = make_site({"/home": "real@example.com"}, redirects={"/": "/home"})
        result = crawler().crawl(f"{base}/")
        assert "real@example.com" in {c.email for c in result.contacts}


class TestDNS钉扎:
    def test_连接强制走已校验IP而非重新解析(self, make_site):
        """F6：把不存在的主机名钉到夹具 IP——若连接自行做 DNS 必然失败，能通即证明钉扎生效。"""

        from app.infrastructure.crawler import _PinnedBackend

        base = make_site({"/": "pin@example.com"})
        port = int(base.rsplit(":", 1)[1])
        backend = _PinnedBackend({"nonexistent.invalid": "127.0.0.1"})
        stream = backend.connect_tcp("nonexistent.invalid", port, timeout=5)
        try:
            request = b"GET / HTTP/1.1\r\nHost: pin\r\nConnection: close\r\n\r\n"
            stream.write(request)
            data = b""
            while True:
                chunk = stream.read(4096, timeout=5)
                if not chunk:
                    break
                data += chunk
            assert b"pin@example.com" in data
        finally:
            stream.close()


class TestSSRF地址判定:
    def test_私网主机拒绝(self):
        from app.infrastructure.crawler import _host_is_fetchable

        assert _host_is_fetchable("192.168.1.1", allow_loopback=False) is False
        assert _host_is_fetchable("10.0.0.5", allow_loopback=False) is False

    def test_解析失败拒绝(self):
        from app.infrastructure.crawler import _host_is_fetchable

        assert _host_is_fetchable("nonexistent.invalid", allow_loopback=False) is False


class Test具名联系人:
    def test_页面上的姓名邮箱对进具名联系人带职位(self, make_site):
        base = make_site({
            "/": 'Contact our Sales Manager John Smith: john@example.com',
        })
        result = crawler().crawl(f"{base}/")
        assert len(result.contacts) == 1
        c = result.contacts[0]
        assert c.name == "John Smith"
        assert c.email == "john@example.com"
        assert "sales" in c.title.lower()

    def test_具名与裸邮箱并存不重复(self, make_site):
        base = make_site({
            "/": 'Anna Kim: anna@example.com | general: info@example.com',
        })
        result = crawler().crawl(f"{base}/")
        by_email = {c.email: c for c in result.contacts}
        assert by_email["anna@example.com"].name == "Anna Kim"
        assert by_email["info@example.com"].name is None
        assert len(result.contacts) == 2
