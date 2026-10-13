"""jobs kind adds discover_buyers

Revision ID: c41f8d2a6e01
Revises: fcaacfb8b462
Create Date: 2026-10-13 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = 'c41f8d2a6e01'
down_revision: str | Sequence[str] | None = 'fcaacfb8b462'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('ck_jobs_kind', 'jobs', type_='check')
    op.create_check_constraint(
        'ck_jobs_kind', 'jobs',
        "kind IN ('send_email','find_contacts','crawl_website','poll_imap','verify_email','discover_buyers')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE kind='discover_buyers'")
    op.drop_constraint('ck_jobs_kind', 'jobs', type_='check')
    op.create_check_constraint(
        'ck_jobs_kind', 'jobs',
        "kind IN ('send_email','find_contacts','crawl_website','poll_imap','verify_email')"
    )
