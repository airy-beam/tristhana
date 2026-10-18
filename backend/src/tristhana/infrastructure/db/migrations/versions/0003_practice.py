"""practice details (PR-02, PR-03, PR-05)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19

Expand/contract: the previous revision keeps serving while this runs (ADR-0014).
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    # The app and backup roles get access through the default privileges (0001, backup_role).
    op.create_table(
        "practice",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("context", sa.Text()),
        sa.Column("online", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("series", ARRAY(sa.Text())),
        sa.Column("end_item", sa.Text()),
        sa.Column("first_part", sa.Text()),
        sa.Column("duration_min", sa.SmallInteger()),
        sa.Column("start_time", sa.Time()),
        sa.Column("timezone", sa.Text()),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint("slot = 1", name="practice_slot_check"),
        sa.CheckConstraint(
            "context IN ('mysore', 'led', 'private', 'self')", name="practice_context_check"
        ),
        sa.CheckConstraint("NOT (context = 'self' AND online)", name="practice_self_offline_check"),
        sa.CheckConstraint(
            "first_part IN ('first_half', 'second_half')", name="practice_first_part_check"
        ),
        sa.CheckConstraint(
            "(end_item IS NULL AND first_part IS NULL) OR coalesce(cardinality(series), 0) > 0",
            name="practice_series_given_check",
        ),
        sa.CheckConstraint("cardinality(series) <= 6", name="practice_series_max_check"),
        sa.CheckConstraint("duration_min BETWEEN 1 AND 600", name="practice_duration_check"),
        sa.CheckConstraint(
            "start_time IS NULL OR timezone IS NOT NULL", name="practice_start_time_zone_check"
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "local_date"],
            ["tristhana.day_log.account_id", "tristhana.day_log.local_date"],
            name="practice_day_log_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "local_date", "slot", name="practice_pkey"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("practice", schema=SCHEMA)
