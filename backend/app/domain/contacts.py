"""联系人领域规则：邮箱规范化、有效性、通用邮箱判定、去重键、
补全置信度、收件人排序、页面信息抽取（纯函数）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 无人名的公共收件箱前缀：命中即 is_generic，不与具名联系人混用
GENERIC_LOCAL_PARTS = frozenset(
    {
        "info", "sales", "contact", "contacts", "hello", "support", "admin",
        "inquiry", "enquiry", "office", "mail", "team", "service", "marketing",
        "customerservice", "customerservices", "reception", "frontdesk",
    }
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_EXTRACT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_EXTRACT_RE = re.compile(r"\+\d{1,3}[\s(-]?\d{1,4}[\s)-]?\d{3,4}[\s-]?\d{0,4}")

# 具名联系人：姓名与邮箱成对出现（"Name: email" / "Name (email)" / "email (Name)" / "Name <email>"）
_PERSON_NAME = r"[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,2}"
_EMAIL_ADDR = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
_NAMED_PATTERNS = (
    re.compile(rf"({_PERSON_NAME})\s*[:(\[\-—]\s*({_EMAIL_ADDR})"),
    re.compile(rf"({_EMAIL_ADDR})\s*[(\[—：]\s*({_PERSON_NAME})\s*[)\]]"),
    re.compile(rf"({_PERSON_NAME})\s*<({_EMAIL_ADDR})>"),
)
# 名字前常被吞进来的礼貌词/动词，从姓名头部剥掉
_NAME_LEADING_NOISE = (
    "contact", "email", "mail", "reach", "ask", "call", "write", "please",
    "mr", "mrs", "ms", "dr", "and", "or", "the", "our", "to", "at", "for",
)
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
# 职位线索：出现在邮箱前 60 字内的这些词，取含词的短语作 title
_TITLE_TOKENS = (
    "sales", "purchas", "procure", "buy", "sourcing", "marketing", "export",
    "manager", "director", "ceo", "owner", "founder", "contact", "head",
)


def extract_named_contacts(text: str) -> list[tuple[str, str, str]]:
    """从页面文本抽「(姓名, 邮箱, 职位猜测)」；脚本/样式块剔除；无姓名不进列表。"""
    cleaned = _SCRIPT_STYLE_RE.sub(" ", text or "")
    seen: set[str] = set()
    result: list[tuple[str, str, str]] = []
    for pattern in _NAMED_PATTERNS:
        for match in pattern.finditer(cleaned):
            first, second = match.group(1), match.group(2)
            # 反向形态：group1 是邮箱
            email, name = (first, second) if "@" in first else (second, first)
            email = email.rstrip(".,;:!?").strip()
            words = name.split()
            noise = set(_NAME_LEADING_NOISE) | set(_TITLE_TOKENS)
            while words and words[0].lower().strip(".,;:") in noise:
                words.pop(0)
            name = " ".join(words)
            if not name:
                continue
            if email.lower() in seen:
                continue
            seen.add(email.lower())
            window = cleaned[max(0, match.start() - 60):match.start()].lower()
            title = ""
            for token in _TITLE_TOKENS:
                idx = window.rfind(token)
                if idx >= 0:
                    snippet = window[idx:].strip(" .,;:->|'\"")
                    title = snippet[:40].strip().title()
                    break
            result.append((name.strip(), email, title))
    return result


def normalize_email(raw: str | None) -> str | None:
    """strip + 小写；空输入返回 None（存 NULL，不参与唯一约束）。"""
    if raw is None:
        return None
    text = raw.strip().lower()
    return text or None


def is_valid_email(email: str) -> bool:
    """最低限度格式校验（本地@域.后缀，无空白）：用于录入拒绝，不做真实可达性判断。"""
    return bool(_EMAIL_RE.match(email.strip()))


def is_generic_email(email: str) -> bool:
    """公共收件箱前缀（info@/sales@ 等）视为通用邮箱，界面打标签、不与具名联系人混用。"""
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return False
    local = normalized.split("@", 1)[0]
    return local in GENERIC_LOCAL_PARTS


def contact_dedup_key(company_id: int, email: str | None) -> tuple[int, str] | None:
    """公司内去重键（规范化邮箱）；无邮箱返回 None（不参与唯一约束，可多条）。"""
    normalized = normalize_email(email)
    if normalized is None:
        return None
    return company_id, normalized


# ---------- WP4：补全与抓取 ----------


@dataclass(frozen=True)
class RecipientCandidate:
    """pick_best_recipient 的输入（发信收件人排序，规则见 DEV-SPEC 3.7 第 4 条）。"""

    contact_id: int
    name: str | None
    title: str
    verify_status: str
    is_generic: bool


# 职位含这些词的联系人优先（采购决策链）
_TITLE_PRIORITY_TOKENS = ("purchas", "procure", "buyer", "sourcing", "import", "采购")


def pick_best_recipient(candidates: list[RecipientCandidate]) -> RecipientCandidate | None:
    """具名且 valid > 具名且 unknown > 通用邮箱；同级职位关键词优先；再按 id 稳定。"""
    if not candidates:
        return None

    def sort_key(c: RecipientCandidate) -> tuple[int, int, int]:
        if not c.is_generic and c.name:
            tier = 0 if c.verify_status == "valid" else 1
        else:
            tier = 2
        title = c.title.lower()
        title_bonus = 0 if any(t in title for t in _TITLE_PRIORITY_TOKENS) else 1
        return tier, title_bonus, c.contact_id

    return min(candidates, key=sort_key)


def website_confidence(
    found_name: str,
    company_normalized_name: str,
    found_country: str = "",
    company_country: str = "",
) -> str:
    """补全服务返回的域名候选置信度（DEV-SPEC 3.7 第 1 条）。

    high：公司名（规范化后）完全一致且国家一致 → 自动采用并继续查联系人；
    medium：公司名一致但国家对不上 → 候选，需人工确认；
    low：公司名对不上 → 仅记录候选。
    """
    from app.domain.normalize import normalize_company_name

    if not found_name or not found_name.strip():
        return "low"
    if normalize_company_name(found_name) != company_normalized_name:
        return "low"
    if (found_country or "").strip().upper() == (company_country or "").strip().upper():
        return "high"
    return "medium"


def extract_emails(text: str) -> list[str]:
    """从页面文本抽取邮箱（去重保序，剥尾部标点）；mailto: 链接同样命中。"""
    seen: list[str] = []
    for hit in _EMAIL_EXTRACT_RE.findall(text or ""):
        email = hit.rstrip(".,;:!?")
        if email.lower() not in {e.lower() for e in seen}:
            seen.append(email)
    return seen


def extract_phones(text: str) -> list[str]:
    """从页面文本抽取国际格式电话（+国家码开头，宽松匹配，去重保序）。"""
    seen: list[str] = []
    for hit in _PHONE_EXTRACT_RE.findall(text or ""):
        phone = hit.strip().rstrip(".,;:")
        if phone not in seen:
            seen.append(phone)
    return seen


def select_crawl_pages(base_url: str, hrefs: list[str], max_pages: int = 5) -> list[str]:
    """首页 + 路径含 contact/about/team 的同站链接，总量封顶 max_pages（首页必占一位）。

    跨域、非 http(s)、重复链接一律不抓。
    """
    from urllib.parse import urljoin, urlparse

    def normalize(url: str) -> str | None:
        absolute = urljoin(base_url, url.strip())
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            return None
        if parsed.netloc != urlparse(base_url).netloc:
            return None
        return absolute

    selected = [base_url]
    base_path = urlparse(base_url).path or "/"
    for href in hrefs:
        url = normalize(href)
        if url is None or url in selected:
            continue
        if urlparse(url).path == base_path:
            continue
        path = urlparse(url).path.lower()
        if any(token in path for token in ("contact", "about", "team")):
            selected.append(url)
        if len(selected) >= max_pages:
            break
    return selected
