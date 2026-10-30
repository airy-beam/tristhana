"""home city: the person's own city drives the zone

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-30

Expand-only (ADR-0014, MD-04, ADR-0029): a nullable column; the previous revision ignores it.
NULL = never chosen, '-' = not listed / not now, otherwise a city slug. No FK: cities live in
YAML (ADR-0019), so `city.tz == timezone` is a domain rule; the DB checks what it can see.
No backfill: a city is never guessed from a zone.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def upgrade() -> None:
    op.add_column("account", sa.Column("home_city", sa.Text(), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        op.f("account_home_city_check"), "account", "home_city ~ '^[a-z-]{1,24}$'", schema=SCHEMA
    )
    op.create_check_constraint(
        op.f("account_home_city_zone_check"),
        "account",
        "home_city IS NULL OR home_city = '-' OR timezone IS NOT NULL",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("account", "home_city", schema=SCHEMA)  # drops its checks with it
