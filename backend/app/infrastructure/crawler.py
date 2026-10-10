"""企业官网抓取（WP4）：只抓公开页，遵守 robots.txt，限速，SSRF 防护。

约束（DEV-SPEC 3.6）：首页 + contact/about/team 链接最多 5 页；同主机间隔 ≥2s；
单页 ≤1MB；仅 http/https；解析 IP 拒绝回环/私网/链路本地，重定向后同样校验。
"""

from __future__ import annotations

import ipaddress
import socket
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

from app.domain.contacts import extract_emails, select_crawl_pages
from app.domain.entities import FoundContact

MAX_PAGES = 5
PAGE_BYTE_CAP = 1024 * 1024
REQUEST_TIMEOUT = 10.0
HOST_INTERVAL = 2.0


def _link_re():
    import re

    global _LINK_RE
    if _LINK_RE is None:
        _LINK_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    return _LINK_RE


_LINK_RE = None


class CrawlBlocked(Exception):
    """robots.txt 不允许或地址非法——确定性放弃，重试无意义（处理器应永久失败）。"""


@dataclass
class CrawlResult:
    pages_fetched: list[str] = field(default_factory=list)
    contacts: list[FoundContact] = field(default_factory=list)
    blocked_reason: str = ""


def _host_is_fetchable(host: str, allow_loopback: bool) -> bool:
    """SSRF 防护：解析全部地址，任一落在回环/私网/链路本地/保留段即拒绝。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback and allow_loopback:
            continue
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            return False
    return True


class WebsiteCrawler:
    def __init__(self, allow_loopback: bool = False) -> None:
        """allow_loopback 仅供本地测试夹具使用（生产默认拒绝回环地址）。"""
        self._allow_loopback = allow_loopback
        self._last_hit: dict[str, float] = {}

    def crawl(self, base_url: str) -> CrawlResult:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise CrawlBlocked(f"官网地址非法：{base_url!r}")
        host = parsed.hostname or ""
        if not _host_is_fetchable(host, self._allow_loopback):
            raise CrawlBlocked("官网主机解析到内网/保留地址，拒绝抓取")

        self._respect_robots(parsed)

        result = CrawlResult()
        emails: dict[str, str] = {}  # email -> 首次出现的页面 URL

        def fetch_and_harvest(url: str) -> str | None:
            html = self._fetch_text(url)
            if html is None:
                return None
            result.pages_fetched.append(url)
            for email in extract_emails(html):
                emails.setdefault(email, url)
            return html

        first_html = fetch_and_harvest(base_url)
        if first_html is None:
            result.blocked_reason = f"首页抓取失败：{base_url}"
            return result

        links = _link_re().findall(first_html)
        for url in select_crawl_pages(base_url, links, MAX_PAGES)[1:]:
            fetch_and_harvest(url)

        result.contacts = [
            FoundContact(name=None, title="", email=email, phone=None, source_ref=f"website:{url}")
            for email, url in emails.items()
        ]
        return result

    def _respect_robots(self, parsed) -> None:
        rp = urllib.robotparser.RobotFileParser()
        body = self._fetch_text(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
        if body is None:
            return  # robots 拿不到按允许处理（业界惯例）
        rp.parse(body.splitlines())
        if not rp.can_fetch("TrueOrder", f"{parsed.scheme}://{parsed.netloc}/"):
            raise CrawlBlocked("robots.txt 不允许抓取该站点")

    def _fetch_text(self, url: str) -> str | None:
        """带 SSRF 复检的重定向跟随（最多 3 跳）+ 限速 + 1MB 上限；失败返回 None。"""
        current = url
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
            for _ in range(4):
                parsed = urlparse(current)
                if parsed.scheme not in ("http", "https"):
                    return None
                host = parsed.hostname or ""
                if not _host_is_fetchable(host, self._allow_loopback):
                    raise CrawlBlocked(f"重定向到内网/保留地址，拒绝：{current}")
                self._throttle(host)
                try:
                    response = client.get(current)
                except httpx.HTTPError:
                    return None
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    continue
                if response.status_code >= 400:
                    return None
                if len(response.content) > PAGE_BYTE_CAP:
                    return None  # 超大页面放弃（不解析半截 HTML）
                return response.text
        return None

    def _throttle(self, host: str) -> None:
        if not self._allow_loopback:  # 测试夹具不限速，保持用例秒级
            now = time.monotonic()
            last = self._last_hit.get(host)
            if last is not None and now - last < HOST_INTERVAL:
                time.sleep(HOST_INTERVAL - (now - last))
            self._last_hit[host] = time.monotonic()
