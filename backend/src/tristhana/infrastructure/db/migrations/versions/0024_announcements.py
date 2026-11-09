"""announcements: a teacher's or a shala's text, mutes and the NT-01 switch

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-09

Expand-only (ADR-0014, NT-03, ADR-0038): one new table, NOT NULL DEFAULT false booleans
(metadata-only on PG >= 11), one nullable column and a wider CHECK, so the previous revision
keeps serving while this runs. Table grants come from the default privileges (0001, 0015).
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"
_CATEGORY = "notification_delivery_category_check"
_MUTED = ("teacher_link", "shala_staff", "shala_student")


def upgrade() -> None:
    op.create_table(
        "announcement",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("shala_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("audience", sa.Integer(), nullable=False),
        sa.Column("pinned_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(text) BETWEEN 1 AND 1000", name=op.f("announcement_text_check")
        ),
        sa.CheckConstraint("audience >= 0", name=op.f("announcement_audience_check")),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["tristhana.account.id"],
            name=op.f("announcement_author_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shala_id"],
            ["tristhana.shala.id"],
            name=op.f("announcement_shala_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("announcement_pkey")),
        schema=SCHEMA,
    )
    op.create_index(
        "announcement_author_id_created_at_idx",
        "announcement",
        ["author_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "announcement_shala_id_created_at_idx",
        "announcement",
        ["shala_id", "created_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("shala_id IS NOT NULL"),
    )
    op.create_index("announcement_created_at_idx", "announcement", ["created_at"], schema=SCHEMA)
    for table in _MUTED:
        op.add_column(
            table,
            sa.Column(
                "announcements_muted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            schema=SCHEMA,
        )
    op.add_column(
        "notification_settings", sa.Column("announcements_on", sa.Boolean()), schema=SCHEMA
    )
    op.execute(
        f'ALTER TABLE {SCHEMA}.notification_delivery DROP CONSTRAINT IF EXISTS "{_CATEGORY}"'
    )
    op.create_check_constraint(
        op.f(_CATEGORY),
        "notification_delivery",
        "category IN ('moon', 'practice', 'announcement')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute("DELETE FROM tristhana.notification_delivery WHERE category = 'announcement'")
    op.drop_constraint(op.f(_CATEGORY), "notification_delivery", schema=SCHEMA)
    op.create_check_constraint(
        op.f(_CATEGORY),
        "notification_delivery",
        "category IN ('moon', 'practice')",
        schema=SCHEMA,
    )
    op.drop_column("notification_settings", "announcements_on", schema=SCHEMA)
    for table in _MUTED:
        op.drop_column(table, "announcements_muted", schema=SCHEMA)
    op.drop_table("announcement", schema=SCHEMA)
