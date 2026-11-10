"""directory_listing: a teacher's checked "listed in the public directory" fact

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-11

Expand-only (ADR-0014, ID-05, ADR-0042): one new table, which the previous revision ignores.
One row per account; it goes with the account, and a deleted checker leaves `checked_by`
NULL (the line stays). No backfill. Table grants come from the default privileges (0001, 0015).
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"


def upgrade() -> None:
    op.create_table(
        "directory_listing",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("name_as_listed", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("declared_level", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("checked_on", sa.Date(), nullable=True),
        sa.Column("checked_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'listed', 'not_found', 'withdrawn')",
            name=op.f("directory_listing_status_check"),
        ),
        sa.CheckConstraint(
            "declared_level IN ('authorised', 'authorised-1', 'authorised-2', 'certified')",
            name=op.f("directory_listing_declared_level_check"),
        ),
        sa.CheckConstraint(
            "char_length(name_as_listed) BETWEEN 1 AND 100"
            " AND char_length(region) BETWEEN 1 AND 60 AND char_length(note) <= 300",
            name=op.f("directory_listing_lengths_check"),
        ),
        sa.CheckConstraint(
            "(status = 'withdrawn') = (name_as_listed IS NULL)"
            " AND (status = 'withdrawn') = (region IS NULL)",
            name=op.f("directory_listing_details_check"),
        ),
        sa.CheckConstraint(
            "status <> 'listed' OR checked_on IS NOT NULL",
            name=op.f("directory_listing_checked_check"),
        ),
        sa.CheckConstraint(
            "note IS NULL OR status = 'pending'", name=op.f("directory_listing_note_check")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name=op.f("directory_listing_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["checked_by"],
            ["tristhana.account.id"],
            name=op.f("directory_listing_checked_by_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("directory_listing_pkey")),
        schema=SCHEMA,
    )
    op.create_index(
        "directory_listing_pending_idx",
        "directory_listing",
        ["requested_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "directory_listing_listed_idx",
        "directory_listing",
        ["checked_on"],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'listed'"),
    )


def downgrade() -> None:
    op.drop_table("directory_listing", schema=SCHEMA)
