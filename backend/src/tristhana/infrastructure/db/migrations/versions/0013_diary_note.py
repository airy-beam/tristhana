"""diary note: one sealed free-text note per account and local day

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-27

Expand-only (ADR-0014, PR-07, ADR-0025): a new table; no data change, and the previous
revision ignores it. The text is sealed (ADR-0016) and the row has no status, so a note
never reveals a 🌸 day; it hangs off the account, not the day log.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    # The app and backup roles get access through the default privileges (0001, backup_role).
    op.create_table(
        "diary_note",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("sealed_text", sa.LargeBinary(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "octet_length(sealed_text) BETWEEN 42 AND 8041", name="diary_note_sealed_length_check"
        ),
        sa.CheckConstraint("local_date >= '2000-01-01'", name="diary_note_local_date_min_check"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="diary_note_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "local_date", name="diary_note_pkey"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("diary_note", schema=SCHEMA)
