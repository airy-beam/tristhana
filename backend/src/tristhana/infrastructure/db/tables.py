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
    # Chosen in settings (ID-06): Telegram's name/language no longer overwrite them.
    Column("name_custom", Boolean(), nullable=False, server_default=text("false")),
    Column("locale_custom", Boolean(), nullable=False, server_default=text("false")),
    # The weekly day off (PR-09, ADR-0022): ISO-weekday bitmask (bit d-1); 0 = none, NULL =
    # never chosen. `day_off_before` was in effect before `day_off_since`.
    Column("day_off", SmallInteger()),
    Column("day_off_since", Date()),
    Column("day_off_before", SmallInteger()),
    Column("day_off_dismissed_at", DateTime(timezone=True)),  # "Not now" on the question
    # WH-01: leave the 🌸 button out of the status grids (bot and Mini App).
    Column("hide_ladies", Boolean(), nullable=False, server_default=text("false")),
    # PR-06: offer the one-tap check-in mood row after logging a practice.
    Column("offer_check_in", Boolean(), nullable=False, server_default=text("true")),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    _timestamp("last_seen_at"),
    CheckConstraint("char_length(display_name) <= 64", name="display_name_length"),
    CheckConstraint("locale IN ('en', 'ru')", name="locale"),
    CheckConstraint("moon_location ~ '^[a-z-]{1,24}$'", name="moon_location"),
    CheckConstraint("day_off BETWEEN 0 AND 127", name="day_off"),
    CheckConstraint("day_off_before BETWEEN 0 AND 127", name="day_off_before"),
    CheckConstraint("day_off_before IS NULL OR day_off_since IS NOT NULL", name="day_off_period"),
    CheckConstraint("day_off_since IS NULL OR day_off IS NOT NULL", name="day_off_since_set"),
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

# WH-01 part 2 (ADR-0023): a 🌸 / sick / travel statement over [start_date, end_date]
# (inclusive). The kind is sealed on every row (one byte, as `day_log.sealed_status`), so a
# 🌸 period is indistinguishable from sick/travel. The 14-day cap keeps the overlap read a
# PK range (`start_date BETWEEN from - 13 AND to`); the 🌸 limit of 7 is a domain rule.
rest_period = Table(
    "rest_period",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("start_date", Date(), nullable=False),
    Column("end_date", Date(), nullable=False, index=True),  # the tick's paused days (0011)
    Column("sealed_kind", LargeBinary(), nullable=False),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "start_date"),
    CheckConstraint("end_date > start_date", name="period_order"),
    CheckConstraint("end_date - start_date <= 13", name="period_length"),
    CheckConstraint("octet_length(sealed_kind) = 42", name="sealed_length"),
    CheckConstraint("start_date >= '2000-01-01'", name="start_date_min"),
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

# PR-06 (ADR-0024): an after-practice check-in per practice slot, plain and owner-only.
# Like `practice`, it exists only on a practiced day (the day upsert deletes it otherwise).
# Tag keys are validated in the domain (no value CHECK), so the vocabulary can grow.
check_in = Table(
    "check_in",
    metadata,
    Column("account_id", Uuid(), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("slot", SmallInteger(), nullable=False, server_default=text("1")),
    Column("mood", SmallInteger()),
    Column("energy", SmallInteger()),
    Column("effort", SmallInteger()),
    Column("tags", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "local_date", "slot"),
    ForeignKeyConstraint(
        ["account_id", "local_date"],
        [day_log.c.account_id, day_log.c.local_date],
        ondelete="CASCADE",
        name="check_in_day_log_fkey",
    ),
    CheckConstraint("slot = 1", name="slot"),
    CheckConstraint("mood BETWEEN 1 AND 5", name="mood"),
    CheckConstraint("energy BETWEEN 1 AND 5", name="energy"),
    CheckConstraint("effort BETWEEN 1 AND 5", name="effort"),
    CheckConstraint("cardinality(tags) <= 16", name="tags_max"),
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
    Column("practice_on", Boolean()),  # NULL = never chosen (the one-time offer may show)
    Column("practice_at", Time()),
    Column("unreachable_at", DateTime(timezone=True)),
    Column("moon_intro_sent_at", DateTime(timezone=True)),  # Q24: the intro went out once
    _timestamp("updated_at"),
    CheckConstraint("moon_offsets <@ '{1,3,7}'::smallint[]", name="moon_offsets"),
    CheckConstraint("daily_cap BETWEEN 1 AND 10", name="daily_cap"),
    CheckConstraint("(quiet_start IS NULL) = (quiet_end IS NULL)", name="quiet_pair"),
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
    CheckConstraint("category IN ('moon', 'practice')", name="category"),
    CheckConstraint("status IN ('claimed', 'sent', 'failed', 'blocked')", name="status"),
)
