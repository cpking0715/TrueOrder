"""contacts source adds wikidata

Revision ID: b52d4c6e8a13
Revises: a7c3e91d5f02
Create Date: 2026-10-12 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b52d4c6e8a13'
down_revision: str | Sequence[str] | None = 'a7c3e91d5f02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_contacts_source', 'contacts', type_='check')
    op.create_check_constraint(
        'ck_contacts_source', 'contacts',
        "source IN ('manual','csv','finder','website','wikidata')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE contacts SET source = 'finder' WHERE source = 'wikidata'")
    op.drop_constraint('ck_contacts_source', 'contacts', type_='check')
    op.create_check_constraint(
        'ck_contacts_source', 'contacts',
        "source IN ('manual','csv','finder','website')"
    )
