"""company_lead_sources：产品×企业的非提单来源线索（AI 买家发现）

Revision ID: c7e1a2d9f480
Revises: b8d2f4a6c913
Create Date: 2026-10-14 21:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7e1a2d9f480'
down_revision: str | Sequence[str] | None = 'b8d2f4a6c913'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'company_lead_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_ref', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("source IN ('ai_discover')", name='ck_lead_source'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'company_id', 'source', name='uq_lead_source'),
    )
    op.create_index('ix_company_lead_sources_company_id', 'company_lead_sources', ['company_id'])
    op.create_index('ix_company_lead_sources_product_id', 'company_lead_sources', ['product_id'])


def downgrade() -> None:
    op.drop_index('ix_company_lead_sources_product_id', table_name='company_lead_sources')
    op.drop_index('ix_company_lead_sources_company_id', table_name='company_lead_sources')
    op.drop_table('company_lead_sources')
