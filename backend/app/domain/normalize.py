"""公司名 / 国家 / 地址 / 税号的归一化规则（纯函数，无 I/O）。"""

from __future__ import annotations

import calendar
import re
from datetime import date

# 法律形态后缀：剥离后参与「规范化名称 + 国家」的企业识别。
LEGAL_SUFFIX_TOKENS = {
    "INC",
    "INCORPORATED",
    "LLC",
    "LTD",
    "LIMITED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "GMBH",
    "AG",
    "SA",
    "SAS",
    "SARL",
    "BV",
    "NV",
    "PLC",
    "PT",
    "TBK",
    "PTE",
    "SDN",
    "BHD",
    "KK",
    "OY",
    "AB",
    "SPA",
    "SRL",
    "LP",
    "LLP",
    "JSC",
    "JOINT",
    "STOCK",
}

# 国家归一化：key 为「去掉非字母后的大写」。
COUNTRY_MAP = {
    "US": "US",
    "USA": "US",
    "UNITEDSTATES": "US",
    "AMERICA": "US",
    "CN": "CN",
    "CHINA": "CN",
    "PRCHINA": "CN",
    "PRC": "CN",
    "MAINLANDCHINA": "CN",
    "PEOPLESREPUBLICOFCHINA": "CN",
    "VN": "VN",
    "VIETNAM": "VN",
    "HK": "HK",
    "HONGKONG": "HK",
    "MX": "MX",
    "MEXICO": "MX",
    "DE": "DE",
    "GERMANY": "DE",
    "DEUTSCHLAND": "DE",
    "GB": "GB",
    "UK": "GB",
    "UNITEDKINGDOM": "GB",
    "GREATBRITAIN": "GB",
    "ENGLAND": "GB",
    "CA": "CA",
    "CANADA": "CA",
    "JP": "JP",
    "JAPAN": "JP",
    "KR": "KR",
    "KOREA": "KR",
    "SOUTHKOREA": "KR",
    "TW": "TW",
    "TAIWAN": "TW",
    "SG": "SG",
    "SINGAPORE": "SG",
    "MY": "MY",
    "MALAYSIA": "MY",
    "TH": "TH",
    "THAILAND": "TH",
    "IN": "IN",
    "INDIA": "IN",
    "FR": "FR",
    "FRANCE": "FR",
    "IT": "IT",
    "ITALY": "IT",
    "ES": "ES",
    "SPAIN": "ES",
    "NL": "NL",
    "NETHERLANDS": "NL",
    "AU": "AU",
    "AUSTRALIA": "AU",
    "BR": "BR",
    "BRAZIL": "BR",
}

ISO3_TO_ISO2 = {
    "USA": "US",
    "CHN": "CN",
    "VNM": "VN",
    "HKG": "HK",
    "MEX": "MX",
    "DEU": "DE",
    "GBR": "GB",
    "CAN": "CA",
    "JPN": "JP",
    "KOR": "KR",
    "TWN": "TW",
    "SGP": "SG",
    "MYS": "MY",
    "THA": "TH",
    "IND": "IN",
    "FRA": "FR",
    "ITA": "IT",
    "ESP": "ES",
    "NLD": "NL",
    "AUS": "AU",
    "BRA": "BR",
}


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().upper()


def normalize_company_name(name: str) -> str:
    """大写、去标点、合并空白、从尾部逐层剥离法律形态后缀。"""
    tokens = [t for t in re.split(r"[^A-Z0-9]+", (name or "").upper()) if t]
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIX_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def normalize_country(raw: str) -> str:
    """常见写法映射到 ISO2；未知两位字母原样大写；其余返回去符号大写原文。"""
    key = re.sub(r"[^A-Za-z]", "", raw or "").upper()
    if not key:
        return ""
    if key in COUNTRY_MAP:
        return COUNTRY_MAP[key]
    if len(key) == 3 and key in ISO3_TO_ISO2:
        return ISO3_TO_ISO2[key]
    return key


# 美式地址「... , 城市 州 ZIP」，城市与州之间用空格分隔。
_CITY_STATE_ZIP = re.compile(r",\s*([A-Za-z][A-Za-z .'\-]*?)\s+[A-Za-z]{2}\s+\d{4,5}(?:-\d{4})?")
_ALPHA_SEGMENT = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")


def guess_city(address: str) -> str:
    """美式「城市, 州 ZIP」优先；否则取第一个纯字母段；找不到返回空串。"""
    text = (address or "").strip()
    if not text:
        return ""
    m = _CITY_STATE_ZIP.search(text)
    if m:
        return _squash(m.group(1))
    for segment in text.split(","):
        seg = segment.strip()
        if seg and _ALPHA_SEGMENT.match(seg):
            return _squash(seg)
    return ""


def name_conflict(variants: list[tuple[str, str]]) -> bool:
    """同一规范化名称 + 国家下出现多个不同城市线索时，视为同名冲突（只标记不合并）。"""
    cities = {guess_city(addr) for _, addr in variants}
    cities.discard("")
    return len(cities) > 1


_HS_RE = re.compile(r"^\d{6}(\d{0,4})$")


def is_valid_hs(code: str) -> bool:
    """6~10 位纯数字且前 6 位非全零才算有效；否则按税号误码处理。"""
    c = (code or "").strip()
    return bool(_HS_RE.match(c)) and c[:6] != "000000"


def hs_family_prefix(code: str) -> str:
    """税号族（4 位标题）前缀，用于把误码票也归到产品上下文里。"""
    return (code or "")[:4]


def months_before(d: date, months: int) -> date:
    """按自然月回推，日期溢出时取当月最后一天。"""
    total = d.year * 12 + (d.month - 1) - months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
