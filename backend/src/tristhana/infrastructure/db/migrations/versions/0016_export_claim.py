"""export claim: one export per account per 10 minutes

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-27

Expand-only (ADR-0014, ST-09, ADR-0027): a nullable column; the previous revision ignores it.
`export_claimed_at` is the rate-limit slot, claimed in one statement and released when sending
fails. Account deletion needs no migration: every per-account FK already cascades.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("export_claimed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("account", "export_claimed_at", schema=SCHEMA)
