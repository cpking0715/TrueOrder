"""enrichment_calls.company_id 可空：AI 调用（税号推荐/买家发现）入审计与日额度

Revision ID: e3a9c1b7d402
Revises: f94260c0dfa5
Create Date: 2026-10-14 10:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e3a9c1b7d402'
down_revision: str | Sequence[str] | None = 'f94260c0dfa5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column('enrichment_calls', 'company_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM enrichment_calls WHERE company_id IS NULL")
    op.alter_column('enrichment_calls', 'company_id', existing_type=sa.Integer(), nullable=False)
