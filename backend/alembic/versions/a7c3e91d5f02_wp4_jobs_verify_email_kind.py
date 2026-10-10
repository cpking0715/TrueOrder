"""wp4 jobs kind adds verify_email

Revision ID: a7c3e91d5f02
Revises: 209d5470bed4
Create Date: 2026-10-10 17:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c3e91d5f02'
down_revision: Union[str, Sequence[str], None] = '209d5470bed4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_jobs_kind', 'jobs', type_='check')
    op.create_check_constraint(
        'ck_jobs_kind', 'jobs',
        "kind IN ('send_email','find_contacts','crawl_website','poll_imap','verify_email')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_jobs_kind', 'jobs', type_='check')
    op.create_check_constraint(
        'ck_jobs_kind', 'jobs',
        "kind IN ('send_email','find_contacts','crawl_website','poll_imap')"
    )
