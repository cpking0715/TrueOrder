"""company_lead_sources 增加联系人来源（官网/Hunter/手动）并回填可推出产品上下文的历史联系人

Revision ID: d4f6b8a1c235
Revises: c7e1a2d9f480
Create Date: 2026-10-14 22:10:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = 'd4f6b8a1c235'
down_revision: str | Sequence[str] | None = 'c7e1a2d9f480'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = "source IN ('ai_discover','contact_website','contact_hunter','contact_manual')"


def upgrade() -> None:
    op.drop_constraint('ck_lead_source', 'company_lead_sources', type_='check')
    op.create_check_constraint('ck_lead_source', 'company_lead_sources', NEW)
    from app.infrastructure.lead_sources import backfill_contact_leads

    stats = backfill_contact_leads(op.get_bind())
    print(f"contact leads backfill: {stats}")


def downgrade() -> None:
    op.execute("DELETE FROM company_lead_sources WHERE source LIKE 'contact_%'")
    op.drop_constraint('ck_lead_source', 'company_lead_sources', type_='check')
    op.create_check_constraint('ck_lead_source', 'company_lead_sources', "source IN ('ai_discover')")
