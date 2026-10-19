"""Table definitions (SQLAlchemy Core, no ORM). Migrations must match: `alembic check`."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    Time,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY

SCHEMA = "tristhana"

metadata = MetaData(
    schema=SCHEMA,
    naming_convention={
        "ix": "%(table_name)s_%(column_0_name)s_idx",
        "ck": "%(table_name)s_%(constraint_name)s_check",
        "fk": "%(table_name)s_%(column_0_name)s_fkey",
        "pk": "%(table_name)s_pkey",
    },
)


def _timestamp(name: str) -> Column[datetime]:
    return Column(name, DateTime(timezone=True), nullable=False, server_default=func.now())


account = Table(
    "account",
    metadata,
    Column("id", Uuid(), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("display_name", Text()),
    Column("locale", Text(), nullable=False),
    Column("timezone", Text()),  # IANA name (ADR-0005); NULL until the device reports it
    Column("moon_location", Text()),  # city slug (MD-03); NULL = the default (Mysuru)
    _timestamp("created_at"),
    _timestamp("updated_at"),
    _timestamp("last_seen_at"),
    CheckConstraint("char_length(display_name) <= 64", name="display_name_length"),
    CheckConstraint("locale IN ('en', 'ru')", name="locale"),
    CheckConstraint("moon_location ~ '^[a-z-]{1,24}$'", name="moon_location"),
)

identity = Table(
    "identity",
    metadata,
    Column("provider", Text(), primary_key=True),
    Column("provider_user_id", Text(), primary_key=True),
    Column(
        "account_id",
        Uuid(),
        ForeignKey(account.c.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    _timestamp("created_at"),
    CheckConstraint("provider IN ('telegram')", name="provider"),
)

# PR-01. `status` is the public value: a ladies' holiday is stored as 'rest', and every
# 'rest' row carries `sealed_status` (the true value, encrypted), so the two are
# indistinguishable here (ADR-0016). 'ladies' is not a valid plain value.
day_log = Table(
    "day_log",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("status", Text(), nullable=False),
    Column("sealed_status", LargeBinary()),
    Column("timezone", Text()),  # zone "today" was computed in; NULL = provisional guess
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "local_date"),
    CheckConstraint(
        "status IN ('practiced', 'rest', 'moon', 'sick', 'travel', 'skipped')", name="status"
    ),
    CheckConstraint("(status = 'rest') = (sealed_status IS NOT NULL)", name="sealed_rest"),
    # key id (1) + nonce (24) + 1-byte payload + tag (16): every seal has the same length.
    CheckConstraint("octet_length(sealed_status) = 42", name="sealed_length"),
    CheckConstraint("local_date >= '2000-01-01'", name="local_date_min"),
)

# PR-02/03/05. One practice per practiced day for now (slot 1). Lengths reference the catalog
# by natural key, validated in the domain (ADR-0017: no catalog tables, no FKs).
practice = Table(
    "practice",
    metadata,
    Column("account_id", Uuid(), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("slot", SmallInteger(), nullable=False, server_default=text("1")),
    Column("context", Text()),
    Column("online", Boolean(), nullable=False, server_default=text("false")),
    Column("series", ARRAY(Text())),  # NULL: length not given; '{}': short practice
    Column("end_item", Text()),
    Column("first_part", Text()),
    Column("duration_min", SmallInteger()),
    Column("start_time", Time()),  # wall clock in `timezone` (ADR-0005)
    Column("timezone", Text()),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "local_date", "slot"),
    ForeignKeyConstraint(
        ["account_id", "local_date"],
        [day_log.c.account_id, day_log.c.local_date],
        ondelete="CASCADE",
        name="practice_day_log_fkey",
    ),
    CheckConstraint("slot = 1", name="slot"),
    CheckConstraint("context IN ('mysore', 'led', 'private', 'self')", name="context"),
    CheckConstraint("NOT (context = 'self' AND online)", name="self_offline"),
    CheckConstraint("first_part IN ('first_half', 'second_half')", name="first_part"),
    CheckConstraint(
        "(end_item IS NULL AND first_part IS NULL) OR coalesce(cardinality(series), 0) > 0",
        name="series_given",
    ),
    CheckConstraint("cardinality(series) <= 6", name="series_max"),
    CheckConstraint("duration_min BETWEEN 1 AND 600", name="duration"),
    CheckConstraint("start_time IS NULL OR timezone IS NOT NULL", name="start_time_zone"),
)

# MD-03 / ADR-0019: stored moon calendars per city (previous year … current + 2).
moon_calendar = Table(
    "moon_calendar",
    metadata,
    Column("location", Text(), nullable=False),
    Column("year", SmallInteger(), nullable=False),
    Column("algo_version", Text(), nullable=False),
    _timestamp("computed_at"),
    PrimaryKeyConstraint("location", "year"),
)

moon_day = Table(
    "moon_day",
    metadata,
    Column("location", Text(), nullable=False),
    Column("date", Date(), nullable=False),
    Column("kind", Text(), nullable=False),
    PrimaryKeyConstraint("location", "date"),
    CheckConstraint(
        "kind IN ('purnima', 'amavasya', 'kshaya_purnima', 'kshaya_amavasya')", name="kind"
    ),
)

# MD-03 / ADR-0018. A missing row or NULL column means the domain default.
notification_settings = Table(
    "notification_settings",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), primary_key=True),
    Column("moon_offsets", ARRAY(SmallInteger())),
    Column("moon_at", Time()),
    Column("quiet_start", Time()),
    Column("quiet_end", Time()),
    Column("daily_cap", SmallInteger()),
    Column("unreachable_at", DateTime(timezone=True)),
    _timestamp("updated_at"),
    CheckConstraint("moon_offsets <@ '{1,3,7}'::smallint[]", name="moon_offsets"),
    CheckConstraint("daily_cap BETWEEN 1 AND 10", name="daily_cap"),
)

notification_delivery = Table(
    "notification_delivery",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("dedupe_key", Text(), nullable=False),
    Column("category", Text(), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("status", Text(), nullable=False),
    Column("attempts", SmallInteger(), nullable=False, server_default=text("1")),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "dedupe_key"),
    CheckConstraint("category IN ('moon')", name="category"),
    CheckConstraint("status IN ('claimed', 'sent', 'failed', 'blocked')", name="status"),
)
