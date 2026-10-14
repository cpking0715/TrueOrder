"""CSV 导入改后台任务：jobs 增加 import_csv 种类与 result 列，新增 job_uploads 暂存表

Revision ID: b8d2f4a6c913
Revises: e3a9c1b7d402
Create Date: 2026-10-14 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b8d2f4a6c913'
down_revision: str | Sequence[str] | None = 'e3a9c1b7d402'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "kind IN ('send_email','find_contacts','crawl_website','poll_imap','verify_email','discover_buyers')"
NEW = (
    "kind IN ('send_email','find_contacts','crawl_website','poll_imap','verify_email'"
    ",'discover_buyers','import_csv')"
)


def upgrade() -> None:
    op.drop_constraint('ck_jobs_kind', 'jobs', type_='check')
    op.create_check_constraint('ck_jobs_kind', 'jobs', NEW)
    op.add_column('jobs', sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        'job_uploads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('job_uploads')
    op.drop_column('jobs', 'result')
    op.execute("DELETE FROM jobs WHERE kind='import_csv'")
    op.drop_constraint('ck_jobs_kind', 'jobs', type_='check')
    op.create_check_constraint('ck_jobs_kind', 'jobs', OLD)
