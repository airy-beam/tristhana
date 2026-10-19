"""moon calendars and notifications (MD-03, MD-01 storage, NT-01/02)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19

Expand/contract: the previous revision keeps serving while this runs (ADR-0014).
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    # App and backup roles get access through the default privileges (0001, backup_role).
    op.add_column("account", sa.Column("moon_location", sa.Text()), schema=SCHEMA)
    op.create_check_constraint(
        op.f("account_moon_location_check"),  # final name: not re-run through the convention
        "account",
        "moon_location ~ '^[a-z-]{1,24}$'",
        schema=SCHEMA,
    )
    op.create_table(
        "moon_calendar",
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("algo_version", sa.Text(), nullable=False),
        _timestamp("computed_at"),
        sa.PrimaryKeyConstraint("location", "year", name="moon_calendar_pkey"),
        schema=SCHEMA,
    )
    op.create_table(
        "moon_day",
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('purnima', 'amavasya', 'kshaya_purnima', 'kshaya_amavasya')",
            name="moon_day_kind_check",
        ),
        sa.PrimaryKeyConstraint("location", "date", name="moon_day_pkey"),
        schema=SCHEMA,
    )
    op.create_table(
        "notification_settings",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("moon_offsets", ARRAY(sa.SmallInteger())),
        sa.Column("moon_at", sa.Time()),
        sa.Column("quiet_start", sa.Time()),
        sa.Column("quiet_end", sa.Time()),
        sa.Column("daily_cap", sa.SmallInteger()),
        sa.Column("unreachable_at", sa.DateTime(timezone=True)),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "moon_offsets <@ '{1,3,7}'::smallint[]", name="notification_settings_moon_offsets_check"
        ),
        sa.CheckConstraint(
            "daily_cap BETWEEN 1 AND 10", name="notification_settings_daily_cap_check"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="notification_settings_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name="notification_settings_pkey"),
        schema=SCHEMA,
    )
    op.create_table(
        "notification_delivery",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint("category IN ('moon')", name="notification_delivery_category_check"),
        sa.CheckConstraint(
            "status IN ('claimed', 'sent', 'failed', 'blocked')",
            name="notification_delivery_status_check",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="notification_delivery_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "dedupe_key", name="notification_delivery_pkey"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("notification_delivery", schema=SCHEMA)
    op.drop_table("notification_settings", schema=SCHEMA)
    op.drop_table("moon_day", schema=SCHEMA)
    op.drop_table("moon_calendar", schema=SCHEMA)
    op.drop_constraint(op.f("account_moon_location_check"), "account", schema=SCHEMA)
    op.drop_column("account", "moon_location", schema=SCHEMA)
