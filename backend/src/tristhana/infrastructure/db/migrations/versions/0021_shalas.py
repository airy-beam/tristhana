"""shalas: the shala, its staff with roles, its students and single-use staff links

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-07

Expand-only (ADR-0014, SC-01, ADR-0033): four new tables, which the previous revision ignores.
`joined_on` is the member's local date at confirm. Table grants come from the default
privileges (0001, 0015). No backfill.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"
_ROLES = "'{admin,teacher,assistant,office}'::text[]"
_SLUG = "'^[a-z][a-z-]{0,23}$'"


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _fk(table: str, column: str, parent: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"tristhana.{parent}.id"],
        name=op.f(f"{table}_{column}_fkey"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "shala",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("moon_city", sa.Text(), nullable=True),
        sa.Column("online", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("join_code", sa.Text(), nullable=False),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _fk("shala", "owner_id", "account"),
        sa.PrimaryKeyConstraint("id", name=op.f("shala_pkey")),
        sa.UniqueConstraint("join_code", name=op.f("shala_join_code_key")),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 64", name=op.f("shala_name_check")),
        sa.CheckConstraint(f"city ~ {_SLUG}", name=op.f("shala_city_check")),
        sa.CheckConstraint(f"moon_city ~ {_SLUG}", name=op.f("shala_moon_city_check")),
        sa.CheckConstraint("join_code ~ '^[A-Za-z0-9]{16}$'", name=op.f("shala_join_code_check")),
        schema=SCHEMA,
    )
    op.create_index("shala_owner_id_idx", "shala", ["owner_id"], schema=SCHEMA)
    op.create_table(
        "shala_staff",
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("joined_on", sa.Date(), nullable=False),
        _created_at(),
        _fk("shala_staff", "shala_id", "shala"),
        _fk("shala_staff", "account_id", "account"),
        sa.PrimaryKeyConstraint("shala_id", "account_id", name=op.f("shala_staff_pkey")),
        sa.CheckConstraint(f"roles <@ {_ROLES}", name=op.f("shala_staff_roles_check")),
        schema=SCHEMA,
    )
    op.create_index(
        "shala_staff_account_id_created_at_idx",
        "shala_staff",
        ["account_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "shala_student",
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("joined_on", sa.Date(), nullable=False),
        _created_at(),
        _fk("shala_student", "shala_id", "shala"),
        _fk("shala_student", "account_id", "account"),
        sa.PrimaryKeyConstraint("shala_id", "account_id", name=op.f("shala_student_pkey")),
        schema=SCHEMA,
    )
    op.create_index(
        "shala_student_account_id_created_at_idx",
        "shala_student",
        ["account_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "shala_staff_invite",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("shala_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _fk("shala_staff_invite", "shala_id", "shala"),
        _fk("shala_staff_invite", "created_by", "account"),
        sa.PrimaryKeyConstraint("code", name=op.f("shala_staff_invite_pkey")),
        sa.CheckConstraint(
            "code ~ '^[A-Za-z0-9]{16}$'", name=op.f("shala_staff_invite_code_check")
        ),
        sa.CheckConstraint(f"role = ANY ({_ROLES})", name=op.f("shala_staff_invite_role_check")),
        schema=SCHEMA,
    )
    op.create_index(
        "shala_staff_invite_shala_id_idx", "shala_staff_invite", ["shala_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("shala_staff_invite", schema=SCHEMA)
    op.drop_table("shala_student", schema=SCHEMA)
    op.drop_table("shala_staff", schema=SCHEMA)
    op.drop_table("shala", schema=SCHEMA)
