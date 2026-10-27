"""check in: after-practice mood, energy, effort and tags, and account.offer_check_in

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-27

Expand-only (ADR-0014, PR-06, ADR-0024): a new table and a column with a default; no data
change, and the previous revision ignores both. Scores and tag keys are plain and
owner-only by policy; tag values are validated in the domain, so there is no value CHECK.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    # The app and backup roles get access through the default privileges (0001, backup_role).
    op.create_table(
        "check_in",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("mood", sa.SmallInteger()),
        sa.Column("energy", sa.SmallInteger()),
        sa.Column("effort", sa.SmallInteger()),
        sa.Column("tags", ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint("slot = 1", name="check_in_slot_check"),
        sa.CheckConstraint("mood BETWEEN 1 AND 5", name="check_in_mood_check"),
        sa.CheckConstraint("energy BETWEEN 1 AND 5", name="check_in_energy_check"),
        sa.CheckConstraint("effort BETWEEN 1 AND 5", name="check_in_effort_check"),
        sa.CheckConstraint("cardinality(tags) <= 16", name="check_in_tags_max_check"),
        sa.ForeignKeyConstraint(
            ["account_id", "local_date"],
            ["tristhana.day_log.account_id", "tristhana.day_log.local_date"],
            name="check_in_day_log_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "local_date", "slot", name="check_in_pkey"),
        schema=SCHEMA,
    )
    op.add_column(
        "account",
        sa.Column("offer_check_in", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("account", "offer_check_in", schema=SCHEMA)
    op.drop_table("check_in", schema=SCHEMA)
