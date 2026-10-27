"""progression: the current position per account and its event history

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-27

Expand-only (ADR-0014, PR-08, ADR-0026): two new tables; no data change, and the previous
revision ignores them. No backfill: no position is inferred from the log (the screen offers
a suggestion instead).
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    # The app and backup roles get access through the default privileges (0001, backup_role).
    op.create_table(
        "progression",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("series", sa.Text(), nullable=True),
        sa.Column("last_key", sa.Text(), nullable=True),
        sa.Column(
            "items",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("last_event_id", sa.BigInteger(), nullable=True),
        sa.Column("hint_series", sa.Text(), nullable=True),
        sa.Column("hint_key", sa.Text(), nullable=True),
        sa.Column("hint_event_id", sa.BigInteger(), nullable=True),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "(series IS NULL) = (last_key IS NULL)", name="progression_position_check"
        ),
        sa.CheckConstraint("cardinality(items) <= 8", name="progression_items_max_check"),
        sa.CheckConstraint(
            "(hint_series IS NULL) = (hint_key IS NULL)"
            " AND (hint_series IS NULL) = (hint_event_id IS NULL)",
            name="progression_hint_set_check",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="progression_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name="progression_pkey"),
        schema=SCHEMA,
    )
    op.create_table(
        "progression_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("from_series", sa.Text(), nullable=True),
        sa.Column("from_key", sa.Text(), nullable=True),
        sa.Column("to_series", sa.Text(), nullable=True),
        sa.Column("to_key", sa.Text(), nullable=True),
        sa.Column("item", sa.Text(), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("marked_by", sa.Uuid(), nullable=True),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "kind IN ('start', 'given', 'changed', 'item_given', 'item_removed')",
            name="progression_event_kind_check",
        ),
        sa.CheckConstraint(
            "CASE WHEN kind IN ('item_given', 'item_removed')"
            " THEN item IS NOT NULL AND from_key IS NULL AND to_key IS NULL"
            " AND from_series IS NULL AND to_series IS NULL"
            " ELSE item IS NULL END",
            name="progression_event_item_kind_check",
        ),
        sa.CheckConstraint(
            "(from_series IS NULL) = (from_key IS NULL)",
            name="progression_event_from_position_check",
        ),
        sa.CheckConstraint(
            "(to_series IS NULL) = (to_key IS NULL)", name="progression_event_to_position_check"
        ),
        sa.CheckConstraint(
            "occurred_on >= '2000-01-01'", name="progression_event_occurred_on_min_check"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="progression_event_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["marked_by"],
            ["tristhana.account.id"],
            name="progression_event_marked_by_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="progression_event_pkey"),
        schema=SCHEMA,
    )
    op.create_index(
        "progression_event_account_id_idx",
        "progression_event",
        ["account_id", "id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("progression_event", schema=SCHEMA)
    op.drop_table("progression", schema=SCHEMA)
