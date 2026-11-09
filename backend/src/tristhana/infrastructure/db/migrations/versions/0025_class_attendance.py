"""class_attendance: who was at a class occurrence (SC-05)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-09

Expand-only (ADR-0014, SC-05, ADR-0039): one new table, so the previous revision keeps serving
while this runs. Table grants come from the default privileges (0001, 0015). No backfill.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"
_TYPES = "'mysore', 'led', 'private', 'conference', 'pranayama', 'chanting', 'workshop'"


def upgrade() -> None:
    op.create_table(
        "class_attendance",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("class_id", sa.Uuid(), nullable=True),
        sa.Column("occurrence_key", sa.Date(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("class_type", sa.Text(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("zone", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('claimed', 'confirmed')", name=op.f("class_attendance_state_check")
        ),
        sa.CheckConstraint(
            f"class_type IN ({_TYPES})", name=op.f("class_attendance_class_type_check")
        ),
        sa.CheckConstraint(
            "abs(on_date - occurrence_key) <= 12", name=op.f("class_attendance_on_date_check")
        ),
        sa.ForeignKeyConstraint(
            ["shala_id"],
            ["tristhana.shala.id"],
            name=op.f("class_attendance_shala_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["tristhana.shala_class.id"],
            name=op.f("class_attendance_class_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name=op.f("class_attendance_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("class_attendance_pkey")),
        sa.UniqueConstraint(
            "class_id",
            "occurrence_key",
            "account_id",
            name=op.f("class_attendance_occurrence_key"),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "class_attendance_shala_id_on_date_idx",
        "class_attendance",
        ["shala_id", "on_date"],
        schema=SCHEMA,
    )
    op.create_index(
        "class_attendance_account_id_on_date_idx",
        "class_attendance",
        ["account_id", "on_date"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("class_attendance", schema=SCHEMA)
