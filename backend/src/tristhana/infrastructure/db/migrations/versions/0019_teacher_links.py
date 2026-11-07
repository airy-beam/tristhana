"""teacher links: who teaches whom, and each teacher's invite code

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-07

Expand-only (ADR-0014, ID-04, ADR-0030): two new tables, which the previous revision ignores.
`is_primary` holds only an explicit choice; `linked_on` is the student's local date at confirm.
Table and sequence grants come from the default privileges (0001, 0015). No backfill.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"


def upgrade() -> None:
    op.create_table(
        "teacher_link",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("linked_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["tristhana.account.id"],
            name=op.f("teacher_link_student_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["tristhana.account.id"],
            name=op.f("teacher_link_teacher_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("student_id", "teacher_id", name=op.f("teacher_link_pkey")),
        sa.CheckConstraint("student_id <> teacher_id", name=op.f("teacher_link_not_self_check")),
        schema=SCHEMA,
    )
    op.create_index(
        "teacher_link_teacher_id_student_id_idx",
        "teacher_link",
        ["teacher_id", "student_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "teacher_link_one_primary",
        "teacher_link",
        ["student_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_table(
        "teacher_invite",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name=op.f("teacher_invite_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("teacher_invite_pkey")),
        sa.UniqueConstraint("code", name=op.f("teacher_invite_code_key")),
        sa.CheckConstraint("code ~ '^[A-Za-z0-9]{16}$'", name=op.f("teacher_invite_code_check")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("teacher_invite", schema=SCHEMA)
    op.drop_table("teacher_link", schema=SCHEMA)
