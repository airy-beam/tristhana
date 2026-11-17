"""teacher requests: a student of a shala asks, the teacher confirms

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-17

Expand-only (ADR-0014, ID-07 spec §6, ADR-0046): one new table and a wider CHECK, so the
previous revision keeps serving while this runs. No backfill: nobody has asked yet. Table
grants come from the default privileges (0001, 0015).

The three foreign keys cascade (the student, the teacher, the shala), so account delete stays
one statement (ADR-0027). Membership and the Teacher role are a read-time join, not a key: a
row must outlive a leave-and-rejoin, or the 30 days would not hold.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"
_CATEGORY = "notification_delivery_category_check"


def upgrade() -> None:
    op.create_table(
        "teacher_request",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'waiting'"), nullable=False),
        sa.Column("asked_on", sa.Date(), nullable=False),
        sa.Column("quiet_note_agreed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('waiting', 'declined', 'withdrawn', 'approved')",
            name=op.f("teacher_request_state_check"),
        ),
        sa.CheckConstraint("student_id <> teacher_id", name=op.f("teacher_request_not_self_check")),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["tristhana.account.id"],
            name=op.f("teacher_request_student_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["tristhana.account.id"],
            name=op.f("teacher_request_teacher_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shala_id"],
            ["tristhana.shala.id"],
            name=op.f("teacher_request_shala_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("student_id", "teacher_id", name=op.f("teacher_request_pkey")),
        sa.UniqueConstraint("id", name=op.f("teacher_request_id_key")),
        schema=SCHEMA,
    )
    op.create_index(
        "teacher_request_teacher_id_created_at_idx",
        "teacher_request",
        ["teacher_id", "created_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("state = 'waiting'"),
    )
    op.create_index("teacher_request_shala_id_idx", "teacher_request", ["shala_id"], schema=SCHEMA)
    op.create_index(
        "teacher_request_created_at_idx", "teacher_request", ["created_at"], schema=SCHEMA
    )
    op.execute(
        f'ALTER TABLE {SCHEMA}.notification_delivery DROP CONSTRAINT IF EXISTS "{_CATEGORY}"'
    )
    op.create_check_constraint(
        op.f(_CATEGORY),
        "notification_delivery",
        "category IN ('moon', 'practice', 'announcement', 'request')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute("DELETE FROM tristhana.notification_delivery WHERE category = 'request'")
    op.drop_constraint(op.f(_CATEGORY), "notification_delivery", schema=SCHEMA)
    op.create_check_constraint(
        op.f(_CATEGORY),
        "notification_delivery",
        "category IN ('moon', 'practice', 'announcement')",
        schema=SCHEMA,
    )
    op.drop_table("teacher_request", schema=SCHEMA)
