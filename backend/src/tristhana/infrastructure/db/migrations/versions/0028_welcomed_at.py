"""welcomed_at: when the person met the front door (UI-06)

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-16

Expand-only (ADR-0014, UI-06 spec §3, §6): one nullable column, which the previous revision
ignores. No default and no backfill: NULL means "not yet", and whether an existing person
gets the front door or Today is decided from their activity on their first `/start`.
Derivation alone cannot give "shown once": a teacher whose students have not joined yet has
no activity at all. An internal flag like `day_off_dismissed_at`; not exported.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"


def upgrade() -> None:
    op.add_column("account", sa.Column("welcomed_at", sa.DateTime(timezone=True)), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("account", "welcomed_at", schema=SCHEMA)
