"""quiet note agreed

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"


def upgrade() -> None:
    op.add_column(
        "teacher_link",
        sa.Column(
            "quiet_note_agreed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("teacher_link", "quiet_note_agreed", schema=SCHEMA)
