"""按产品买家类型给企业打分：潜在 / 精准 / 排除。

可解释性要求：每条得分/排除理由都携带提单 id，界面要能点回提单。
纯函数，无框架依赖。
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from app.domain.entities import (
    Audience,
    CompanyFacts,
    ProductConfig,
    ScoreReason,
    ScoreResult,
)
from app.domain.normalize import (
    hs_family_prefix,
    is_valid_hs,
    months_before,
    normalize_company_name,
)

ORIGIN_ALLOWED = {"CN", "VN"}

BLANK_PREFIXES = ("TO THE ORDER", "ORDER OF", "TO ORDER")
BANK_TOKENS = {"BANK", "BANCO", "BANQUE"}
FORWARDER_TOKENS = {
    "FORWARDER", "FORWARDING", "FREIGHT", "NVOCC", "3PL", "LOGISTICS", "CARGO",
    "EXPEDITORS", "KUEHNE", "NAGEL", "SCHENKER", "PANALPINA", "DSV", "CEVA",
    "GEODIS", "YUSEN", "KINTETSU",
}
# 集团内部供货判定时，从名称两端剥离的地理词。
GEO_TOKENS = {"USA", "US", "AMERICA", "CN", "CHINA", "VN", "VIETNAM", "HK", "HONGKONG", "OVERSEAS"}


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().upper()


def _is_blank_consignee(normalized_variant: str) -> bool:
    v = normalized_variant.strip()
    return not v or v.startswith(BLANK_PREFIXES)


def _strip_geo(name: str) -> str:
    tokens = [t for t in name.split() if t]
    while tokens and tokens[0] in GEO_TOKENS:
        tokens.pop(0)
    while tokens and tokens[-1] in GEO_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def is_related_party(shipper_normalized: str, company_normalized: str) -> bool:
    """集团内部供货启发式：规范化后相同，或剥离地理词后相同，或一方整体包含另一方。"""
    a, b = (shipper_normalized or "").strip(), (company_normalized or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    core_a, core_b = _strip_geo(a), _strip_geo(b)
    if core_a and core_a == core_b:
        return True
    if len(a.split()) >= 2 and len(b.split()) >= 2 and (a in b or b in a):
        return True
    return False


def _matched_keywords(business_text: str, keywords: tuple[str, ...]) -> tuple[str, ...]:
    text = _squash(business_text)
    return tuple(k for k in keywords if _squash(k) and _squash(k) in text)


def _bill_ids(bills) -> tuple[int, ...]:
    return tuple(b.bill_id for b in bills)


def _excluded(
    product: ProductConfig,
    facts: CompanyFacts,
    audience: Audience,
    code: str,
    text: str,
    bill_ids: tuple[int, ...],
) -> ScoreResult:
    return ScoreResult(
        product_id=product.product_id,
        company_id=facts.company_id,
        audience=audience,
        tier="excluded",
        reasons=(ScoreReason(code=code, text=text, bill_ids=bill_ids),),
        exclusion_code=code,
    )


def score_company(
    product: ProductConfig,
    audience: Audience,
    facts: CompanyFacts,
    as_of: date,
) -> ScoreResult | None:
    """对企业按产品受众打分。返回 None 表示既不入池也无排除价值（如仅旧票）。"""
    codes_for_audience = {a.hs_code for a in product.hs_assignments if a.audience == audience}
    if not codes_for_audience:
        return None

    norm_variants = [normalize_company_name(v) for v in facts.name_variants] or [
        facts.normalized_name
    ]
    real_variants = [v for v in norm_variants if not _is_blank_consignee(v)]
    all_bill_ids = _bill_ids(facts.bills)
    if not real_variants:
        return _excluded(
            product, facts, audience, "EX_BLANK_CONSIGNEE",
            "收货人为空抬头（TO THE ORDER OF），无真实公司名", all_bill_ids,
        )

    business_text = _squash(" ".join(real_variants) + " " + facts.address)
    name_tokens = {tok for v in real_variants for tok in v.split()}
    text_tokens = name_tokens | set(business_text.split())

    if name_tokens & BANK_TOKENS:
        return _excluded(
            product, facts, audience, "EX_BANK",
            "收货人抬头为银行（可能仅作信用证抬头）", all_bill_ids,
        )
    if text_tokens & FORWARDER_TOKENS:
        return _excluded(
            product, facts, audience, "EX_FORWARDER",
            "收货人名称/地址含货代特征词", all_bill_ids,
        )

    family_prefixes = {hs_family_prefix(c) for c in codes_for_audience}
    in_family = [b for b in facts.bills if hs_family_prefix(b.hs_code) in family_prefixes]
    qualifying = [
        b
        for b in in_family
        if not b.hs_suspect
        and is_valid_hs(b.hs_code)
        and b.hs_code[:6] in codes_for_audience
        and b.origin_country in ORIGIN_ALLOWED
        and b.arrival_date >= months_before(as_of, 24)
    ]
    if not qualifying:
        suspect_family = [
            b for b in in_family if b.hs_suspect or not is_valid_hs(b.hs_code)
        ]
        if suspect_family:
            return _excluded(
                product, facts, audience, "EX_HS_INVALID",
                f"该收货人有 {len(suspect_family)} 票税号明显误码，无法确认税号归属",
                _bill_ids(suspect_family),
            )
        return None

    peer_hits = _matched_keywords(business_text, product.peer_keywords)
    buyer_hits = _matched_keywords(business_text, product.buyer_keywords)
    if peer_hits and not buyer_hits:
        return _excluded(
            product, facts, audience, "EX_PEER_OVERSEAS",
            f"公司业务命中同行行业词（{'、'.join(peer_hits)}），疑似同行海外公司",
            all_bill_ids,
        )

    related = [
        b for b in qualifying if is_related_party(b.shipper_normalized, facts.normalized_name)
    ]
    independent = [b for b in qualifying if b not in related]
    if not independent:
        return _excluded(
            product, facts, audience, "EX_RELATED_PARTY",
            "该税号下的票全部为集团内部供货（供货方与收货人同名/关联）",
            _bill_ids(qualifying),
        )

    reasons: list[ScoreReason] = [
        ScoreReason(
            "RECENT_24M",
            f"近 24 个月自中国/越南进口该税号 {len(qualifying)} 票",
            _bill_ids(qualifying),
        )
    ]
    if related:
        reasons.append(
            ScoreReason(
                "IGNORED_RELATED",
                f"{len(related)} 票为集团内部供货，已从重复计数中剔除",
                _bill_ids(related),
            )
        )

    cutoff_12m = months_before(as_of, 12)
    recent_12m = [b for b in independent if b.arrival_date >= cutoff_12m]
    repeat_ok = len(recent_12m) >= 2
    if repeat_ok:
        reasons.append(
            ScoreReason(
                "REPEAT_12M",
                f"近 12 个月重复进口 {len(recent_12m)} 票",
                _bill_ids(recent_12m),
            )
        )

    shipper_counts = Counter(b.shipper_normalized for b in recent_12m)
    top_shipper, top_count = (shipper_counts.most_common(1)[0] if shipper_counts else ("", 0))
    supplier_ok = top_count >= 2
    if supplier_ok:
        supplier_bills = [b for b in recent_12m if b.shipper_normalized == top_shipper]
        reasons.append(
            ScoreReason(
                "SUPPLIER_MATCH",
                f"近 12 个月由 {top_shipper} 稳定供货 {top_count} 票，供货方与税号对应",
                _bill_ids(supplier_bills),
            )
        )

    if product.buyer_keywords:
        business_ok = bool(buyer_hits)
        if business_ok:
            reasons.append(
                ScoreReason(
                    "BUSINESS_MATCH",
                    f"公司业务匹配买家行业词（{'、'.join(buyer_hits)}）",
                    _bill_ids(qualifying),
                )
            )
    else:
        business_ok = True
        reasons.append(
            ScoreReason("BUSINESS_MATCH_SKIPPED", "产品未配置买家行业词，跳过业务匹配", ())
        )

    precise = repeat_ok and supplier_ok and business_ok
    if precise:
        tier = "precise"
    else:
        tier = "potential"
        unmet = []
        if not repeat_ok:
            unmet.append("近 12 个月重复进口")
        if not supplier_ok:
            unmet.append("供货方与税号对应")
        if not business_ok:
            unmet.append("业务类型匹配")
        reasons.append(ScoreReason("PRECISE_UNMET", "未达精准条件：" + "、".join(unmet), ()))

    return ScoreResult(
        product_id=product.product_id,
        company_id=facts.company_id,
        audience=audience,
        tier=tier,
        reasons=tuple(reasons),
        exclusion_code=None,
        shipments=len(qualifying),
        last_arrival=max((b.arrival_date for b in qualifying), default=None),
        suppliers=tuple(sorted({b.shipper_name for b in qualifying if b.shipper_name})),
    )
