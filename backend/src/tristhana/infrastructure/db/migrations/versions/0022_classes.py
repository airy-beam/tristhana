"""classes: the shala's day off and moon policy, class series, exceptions, closures, swap days

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-08

Expand-only (ADR-0014, SC-02, ADR-0034): two new shala columns with a default and four new
tables, which the previous revision ignores. The teacher FK uses `ON DELETE SET NULL
(teacher_id)` (Postgres >= 15; local and Supabase run 17). Table grants come from the default
privileges (0001, 0015). No backfill.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"
_TYPES = "'mysore', 'led', 'private', 'conference', 'pranayama', 'chanting', 'workshop'"


def _shala_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["shala_id"],
        ["tristhana.shala.id"],
        name=op.f(f"{table}_shala_id_fkey"),
        ondelete="CASCADE",
    )


def _teacher_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["shala_id", "teacher_id"],
        ["tristhana.shala_staff.shala_id", "tristhana.shala_staff.account_id"],
        name=op.f(f"{table}_teacher_id_fkey"),
        ondelete="SET NULL (teacher_id)",
    )


def _ts(name: str) -> sa.Column[Any]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.add_column("shala", sa.Column("days_off", sa.SmallInteger(), nullable=True), schema=SCHEMA)
    op.add_column(
        "shala",
        sa.Column("moon_policy", sa.Text(), server_default=sa.text("'closed'"), nullable=False),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("shala_days_off_check"), "shala", "days_off BETWEEN 0 AND 127", schema=SCHEMA
    )
    op.create_check_constraint(
        op.f("shala_moon_policy_check"),
        "shala",
        "moon_policy IN ('closed', 'pranayama', 'open')",
        schema=SCHEMA,
    )
    op.create_table(
        "shala_class",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("online", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("teacher_id", sa.Uuid(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("minutes", sa.SmallInteger(), nullable=False),
        sa.Column("weekdays", sa.SmallInteger(), nullable=False),
        sa.Column("every", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        _shala_fk("shala_class"),
        _teacher_fk("shala_class"),
        sa.PrimaryKeyConstraint("id", name=op.f("shala_class_pkey")),
        sa.CheckConstraint(f"type IN ({_TYPES})", name=op.f("shala_class_type_check")),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 48", name=op.f("shala_class_title_check")
        ),
        sa.CheckConstraint(
            "city IS NULL OR (city ~ '^[a-z][a-z-]{0,23}$' AND online)",
            name=op.f("shala_class_city_check"),
        ),
        sa.CheckConstraint(
            "minutes BETWEEN 15 AND 480 AND extract(epoch FROM start_time) / 60 + minutes <= 1440",
            name=op.f("shala_class_minutes_check"),
        ),
        sa.CheckConstraint("weekdays BETWEEN 0 AND 127", name=op.f("shala_class_weekdays_check")),
        sa.CheckConstraint("every BETWEEN 1 AND 4", name=op.f("shala_class_every_check")),
        sa.CheckConstraint(
            "ends_on IS NULL OR (ends_on >= starts_on AND weekdays > 0)",
            name=op.f("shala_class_ends_on_check"),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "shala_class_shala_id_starts_on_idx",
        "shala_class",
        ["shala_id", "starts_on"],
        schema=SCHEMA,
    )
    op.create_table(
        "shala_class_override",
        sa.Column("class_id", sa.Uuid(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("moved_to", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("minutes", sa.SmallInteger(), nullable=True),
        sa.Column("teacher_id", sa.Uuid(), nullable=True),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["tristhana.shala_class.id"],
            name=op.f("shala_class_override_class_id_fkey"),
            ondelete="CASCADE",
        ),
        _teacher_fk("shala_class_override"),
        sa.PrimaryKeyConstraint("class_id", "on_date", name=op.f("shala_class_override_pkey")),
        sa.CheckConstraint(
            "status IN ('cancelled', 'held')", name=op.f("shala_class_override_status_check")
        ),
        sa.CheckConstraint(
            "abs(moved_to - on_date) <= 6", name=op.f("shala_class_override_moved_to_check")
        ),
        sa.CheckConstraint(
            "minutes BETWEEN 15 AND 480 AND (start_time IS NULL OR "
            "extract(epoch FROM start_time) / 60 + minutes <= 1440)",
            name=op.f("shala_class_override_minutes_check"),
        ),
        sa.CheckConstraint(
            "status IS DISTINCT FROM 'cancelled' OR (moved_to IS NULL AND start_time IS NULL "
            "AND minutes IS NULL AND teacher_id IS NULL)",
            name=op.f("shala_class_override_cancelled_check"),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "shala_class_override_shala_id_on_date_idx",
        "shala_class_override",
        ["shala_id", "on_date"],
        schema=SCHEMA,
    )
    op.create_table(
        "shala_closure",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        _shala_fk("shala_closure"),
        sa.PrimaryKeyConstraint("id", name=op.f("shala_closure_pkey")),
        sa.CheckConstraint(
            "end_date >= start_date AND end_date - start_date <= 91",
            name=op.f("shala_closure_dates_check"),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "shala_closure_shala_id_end_date_idx",
        "shala_closure",
        ["shala_id", "end_date"],
        schema=SCHEMA,
    )
    op.create_table(
        "shala_swap",
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        _shala_fk("shala_swap"),
        sa.PrimaryKeyConstraint("shala_id", "from_date", name=op.f("shala_swap_pkey")),
        sa.UniqueConstraint("shala_id", "to_date", name="shala_swap_shala_id_to_date_key"),
        sa.CheckConstraint(
            "from_date <> to_date AND abs(to_date - from_date) <= 6",
            name=op.f("shala_swap_dates_check"),
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("shala_swap", schema=SCHEMA)
    op.drop_table("shala_closure", schema=SCHEMA)
    op.drop_table("shala_class_override", schema=SCHEMA)
    op.drop_table("shala_class", schema=SCHEMA)
    op.drop_constraint(op.f("shala_moon_policy_check"), "shala", schema=SCHEMA)
    op.drop_constraint(op.f("shala_days_off_check"), "shala", schema=SCHEMA)
    op.drop_column("shala", "moon_policy", schema=SCHEMA)
    op.drop_column("shala", "days_off", schema=SCHEMA)
