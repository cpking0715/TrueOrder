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

import httpcore
import httpx

from app.domain.contacts import extract_emails, extract_named_contacts, select_crawl_pages
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
    return bool(_validated_ips(host, allow_loopback))


def _validated_ips(host: str, allow_loopback: bool) -> list[str]:
    """解析并按策略过滤；全部地址不合规（或解析失败）返回空列表。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    ok: list[str] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback and allow_loopback:
            ok.append(str(ip))
            continue
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            return []
        ok.append(str(ip))
    return ok


class _PinnedBackend(httpcore._backends.sync.SyncBackend):  # noqa: SLF001 - httpcore 未公开该入口
    """DNS 钉扎（F6 防 rebinding）：连接强制走已校验的 IP。

    TLS 的 SNI 与证书校验仍按原主机（httpcore 在 TLS 握手用 origin host），
    恶意域名在校验后改解析也连不到内网——连接地址由我们钉死。
    """

    def __init__(self, pinned: dict[str, str]) -> None:
        super().__init__()
        self._pinned = pinned

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        target = self._pinned.get(host, host)
        return super().connect_tcp(target, port, timeout, local_address, socket_options)


class WebsiteCrawler:
    def __init__(self, allow_loopback: bool = False, ai_extractor=None) -> None:
        """allow_loopback 仅供本地测试夹具使用（生产默认拒绝回环地址）。

        ai_extractor：可选的页面联系人 AI 提取器（DeepSeek 端口实现），
        只处理联系页、失败兜底正则结果。
        """
        self._allow_loopback = allow_loopback
        self._last_hit: dict[str, float] = {}
        self._pinned: dict[str, str] = {}  # host -> 已校验 IP（DNS 钉扎）
        self._ai_extractor = ai_extractor

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
        named: list[FoundContact] = []  # 具名联系人（姓名+职位猜测），优先于裸邮箱
        page_texts: list[tuple[str, str]] = []  # (url, html) 留给 AI 提取（只存联系页）

        def fetch_and_harvest(url: str) -> str | None:
            html = self._fetch_text(url)
            if html is None:
                return None
            result.pages_fetched.append(url)
            for name, email, title in extract_named_contacts(html):
                if email.lower() not in {c.email.lower() for c in named}:
                    named.append(
                        FoundContact(
                            name=name, title=title, email=email,
                            phone=None, source_ref=f"website:{url}",
                        )
                    )
            for email in extract_emails(html):
                emails.setdefault(email, url)
            if any(t in url.lower() for t in ("contact", "about", "team")):
                page_texts.append((url, html[:16000]))
            return html

        first_html = fetch_and_harvest(base_url)
        if first_html is None:
            result.blocked_reason = f"首页抓取失败：{base_url}"
            return result

        links = _link_re().findall(first_html)
        for url in select_crawl_pages(base_url, links, MAX_PAGES)[1:]:
            fetch_and_harvest(url)

        named_emails = {c.email.lower() for c in named}
        bare = [
            FoundContact(name=None, title="", email=email, phone=None, source_ref=f"website:{url}")
            for email, url in emails.items()
            if email.lower() not in named_emails
        ]
        result.contacts = named + bare

        # AI 增强提取：只跑联系页，失败/无 key 不影响正则结果
        if self._ai_extractor is not None and page_texts:
            existing = {c.email.lower() for c in result.contacts}
            for url, text in page_texts[:2]:  # 每次抓取最多 2 次 AI 调用
                try:
                    for c in self._ai_extractor.extract(text, url):
                        if c.email.lower() not in existing:
                            existing.add(c.email.lower())
                            result.contacts.append(
                                FoundContact(
                                    name=c.name, title=c.title, email=c.email,
                                    phone=c.phone, source_ref=f"website-ai:{url}",
                                )
                            )
                except Exception:  # noqa: BLE001 - AI 是增强：任何失败跳过该页
                    continue
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
        """带 SSRF 复检的重定向跟随（最多 3 跳）+ DNS 钉扎 + 限速 + 1MB 上限；失败返回 None。"""
        current = url
        transport = httpx.HTTPTransport()
        # 钉扎后端挂进连接池（httpx 未公开注入点，锁 uv.lock 的 httpcore 版本）
        transport._pool._network_backend = _PinnedBackend(self._pinned)  # noqa: SLF001
        with httpx.Client(
            timeout=REQUEST_TIMEOUT, follow_redirects=False, transport=transport
        ) as client:
            for _ in range(4):
                parsed = urlparse(current)
                if parsed.scheme not in ("http", "https"):
                    return None
                host = parsed.hostname or ""
                ips = _validated_ips(host, self._allow_loopback)
                if not ips:
                    raise CrawlBlocked(f"重定向到内网/保留地址，拒绝：{current}")
                # 钉住本次校验通过的 IP（防 DNS rebinding：连接不再自行解析）
                self._pinned.setdefault(host, ips[0])
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
