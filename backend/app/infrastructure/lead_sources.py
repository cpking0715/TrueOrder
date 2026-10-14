"""联系人 → 产品线索：只在有产品上下文时记录，不向所有产品扇出。

映射（contacts.source → company_lead_sources.source）：
- website（官网抓取）→ contact_website
- finder（Hunter 等计量补全）→ contact_hunter
- manual（手动录入）→ contact_manual
csv 导入 / wikidata 目录偶得邮箱不映射（无产品上下文或非用户指定来源）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.infrastructure.orm import CompanyLeadSourceORM, ContactORM

CONTACT_LEAD_SOURCES: dict[str, str] = {
    "website": "contact_website",
    "finder": "contact_hunter",
    "manual": "contact_manual",
}
LEAD_SOURCE_LABELS: dict[str, str] = {
    "ai_discover": "AI 买家发现",
    "contact_website": "官网抓取联系人",
    "contact_hunter": "Hunter 补全联系人",
    "contact_manual": "手动录入联系人",
}


def _product_id(value: Any) -> int | None:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def record_contact_leads(session: Session, product_id: Any, company_id: int) -> int:
    """按企业现有联系人来源，为该产品记录线索（幂等）。无 product_id 不做任何事。返回写入行数。"""
    pid = _product_id(product_id)
    if pid is None:
        return 0
    sources = set(
        session.scalars(
            select(ContactORM.source).where(
                ContactORM.company_id == company_id,
                ContactORM.source.in_(list(CONTACT_LEAD_SOURCES)),
            )
        )
    )
    written = 0
    for contact_source in sorted(sources):
        result = session.execute(
            pg_insert(CompanyLeadSourceORM)
            .values(
                product_id=pid,
                company_id=company_id,
                source=CONTACT_LEAD_SOURCES[contact_source],
                source_ref=f"contacts:{contact_source}",
            )
            .on_conflict_do_nothing(constraint="uq_lead_source")
            .returning(CompanyLeadSourceORM.id)
        )
        written += len(result.all())
    return written


# 回填：只用能推出产品上下文的关系，按顺序：
#  1) 该企业在某产品有商机（任意阶段）或 AI 发现线索 → 记到这些产品；
#  2) 否则该企业恰好只在一个产品有得分行 → 记到该产品；
#  多产品得分且无商机/发现记录 → 歧义，跳过（不扇出）。
_BACKFILL_SQL = """
WITH contact_sources AS (
    SELECT DISTINCT company_id,
           CASE source WHEN 'website' THEN 'contact_website'
                       WHEN 'finder' THEN 'contact_hunter'
                       WHEN 'manual' THEN 'contact_manual' END AS lead_source
    FROM contacts
    WHERE source IN ('website', 'finder', 'manual')
),
explicit AS (
    SELECT product_id, company_id FROM opportunities
    UNION
    SELECT product_id, company_id FROM company_lead_sources WHERE source = 'ai_discover'
),
scored AS (
    SELECT company_id, MIN(product_id) AS product_id
    FROM company_scores
    GROUP BY company_id
    HAVING COUNT(DISTINCT product_id) = 1
),
ctx AS (
    SELECT product_id, company_id FROM explicit
    UNION
    SELECT s.product_id, s.company_id FROM scored s
    WHERE NOT EXISTS (SELECT 1 FROM explicit e WHERE e.company_id = s.company_id)
)
INSERT INTO company_lead_sources (product_id, company_id, source, source_ref)
SELECT ctx.product_id, cs.company_id, cs.lead_source, 'backfill:contacts'
FROM contact_sources cs JOIN ctx ON ctx.company_id = cs.company_id
ON CONFLICT ON CONSTRAINT uq_lead_source DO NOTHING
"""

_SKIPPED_SQL = """
SELECT COUNT(DISTINCT c.company_id) FROM contacts c
WHERE c.source IN ('website', 'finder', 'manual')
  AND NOT EXISTS (SELECT 1 FROM company_lead_sources l
                  WHERE l.company_id = c.company_id AND l.source LIKE 'contact_%')
"""


def backfill_contact_leads(conn: Connection) -> dict[str, int]:
    """幂等回填；返回 {inserted, companies_without_context}。"""
    inserted = conn.execute(text(_BACKFILL_SQL)).rowcount or 0
    skipped = int(conn.execute(text(_SKIPPED_SQL)).scalar() or 0)
    return {"inserted": int(inserted), "companies_without_context": skipped}


def main() -> None:
    from app.core.config import get_settings
    from app.infrastructure.db import make_engine

    engine = make_engine(get_settings().database_url)
    with engine.begin() as conn:
        print(backfill_contact_leads(conn))


if __name__ == "__main__":
    main()
