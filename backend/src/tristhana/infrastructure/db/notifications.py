"""Notification settings and the delivery ledger (MD-03, ADR-0018)."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Date,
    and_,
    cast,
    delete,
    false,
    func,
    literal,
    or_,
    select,
    true,
    union_all,
    update,
)
from sqlalchemy.dialects.postgresql import INTERVAL, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import Label

from tristhana.application.ports.notifications import (
    Delivery,
    PracticePause,
    ReminderCandidate,
    ReminderPatch,
)
from tristhana.domain.locale import DEFAULT_LOCALE, LOCALES, Locale
from tristhana.domain.notifications import (
    NotificationSettings,
    StoredSettings,
    defaults_for,
    effective,
)
from tristhana.domain.rest_periods import MAX_PERIOD_DAYS
from tristhana.infrastructure.db.accounts import from_mask
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import (
    account,
    day_log,
    identity,
    notification_delivery,
    notification_settings,
    rest_period,
)

MAX_ATTEMPTS = 3
# A claim older than this was cut off mid-send (a tick past its deadline): take it over.
STALE_CLAIM = timedelta(minutes=5)
_S = notification_settings


def _stored(row: Any) -> StoredSettings:
    if row is None:
        return StoredSettings()
    return StoredSettings(
        moon_offsets=frozenset(row.moon_offsets) if row.moon_offsets is not None else None,
        moon_at=row.moon_at,
        quiet_start=row.quiet_start,
        quiet_end=row.quiet_end,
        daily_cap=row.daily_cap,
        practice_on=row.practice_on,
        practice_at=row.practice_at,
    )


def _settings(row: Any, defaults: NotificationSettings) -> NotificationSettings:
    """A stored row (or None) over the defaults: NULL columns mean "the default"."""
    return effective(_stored(row), defaults)


_SORTED = {"moon_offsets"}


def _pause_columns(account_id: UUID, today: date) -> tuple[Label[Any], Label[Any]]:
    """Scalar subqueries: the rest period covering `today` (WH-01), dates only: the kind
    stays sealed (this adapter has no cipher, and needs none). The latest start wins
    should two ever overlap (writes are serialised per account, ADR-0023)."""
    r = rest_period
    covering = (
        select(r.c.start_date, r.c.end_date)
        .where(
            r.c.account_id == account_id,
            r.c.start_date.between(today - timedelta(days=MAX_PERIOD_DAYS - 1), today),
            r.c.end_date >= today,
        )
        .order_by(r.c.start_date.desc())
        .limit(1)
        .subquery("covering")
    )
    return (
        select(covering.c.start_date).scalar_subquery().label("pause_start"),
        select(covering.c.end_date).scalar_subquery().label("pause_end"),
    )


def _pause(row: Any) -> PracticePause | None:
    return (
        PracticePause(row.pause_start, row.pause_end) if row.pause_start is not None else None
    )  # arrays are stored sorted


_SETTINGS_COLUMNS = (
    _S.c.moon_offsets,
    _S.c.moon_at,
    _S.c.quiet_start,
    _S.c.quiet_end,
    _S.c.daily_cap,
    _S.c.practice_on,
    _S.c.practice_at,
)


class SqlNotificationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def settings(
        self, account_id: UUID, defaults: NotificationSettings
    ) -> NotificationSettings:
        stmt = select(*_SETTINGS_COLUMNS).where(_S.c.account_id == account_id)
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        return _settings(row, defaults)

    async def settings_with_pause(
        self, account_id: UUID, defaults: NotificationSettings, today: date
    ) -> tuple[NotificationSettings, PracticePause | None]:
        one = select(literal(1).label("one")).subquery("one")
        stmt = select(*_SETTINGS_COLUMNS, *_pause_columns(account_id, today)).select_from(
            one.outerjoin(_S, _S.c.account_id == account_id)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return _settings(row, defaults), _pause(row)  # all NULL (no row) = the defaults

    async def save(
        self, account_id: UUID, settings: NotificationSettings, with_practice: bool = True
    ) -> NotificationSettings:
        values: dict[str, Any] = {
            "moon_offsets": sorted(settings.moon.offsets),
            "moon_at": settings.moon.at,
            "quiet_start": settings.quiet.start,
            "quiet_end": settings.quiet.end,
            "daily_cap": settings.daily_cap,
        }
        if with_practice:
            values |= {
                "practice_on": settings.practice.on,
                "practice_at": settings.practice.at,
            }
        return await self._upsert(account_id, values, settings)

    async def stored_row(self, account_id: UUID) -> StoredSettings:
        stmt = select(*_SETTINGS_COLUMNS).where(_S.c.account_id == account_id)
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        return _stored(row)

    async def patch(
        self, account_id: UUID, columns: dict[str, object], defaults: NotificationSettings
    ) -> NotificationSettings:
        values: dict[str, Any] = {
            k: sorted(v) if k in _SORTED and isinstance(v, frozenset) else v  # pyright: ignore[reportUnknownArgumentType]
            for k, v in columns.items()
        }
        return await self._upsert(account_id, values, defaults)

    async def mark_intro_sent(self, account_id: UUID, at: datetime) -> None:
        stmt = insert(_S).values(account_id=account_id, moon_intro_sent_at=at)
        stmt = stmt.on_conflict_do_update(
            index_elements=[_S.c.account_id],
            set_={"moon_intro_sent_at": func.coalesce(_S.c.moon_intro_sent_at, at)},
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def patch_practice(
        self, account_id: UUID, patch: ReminderPatch, defaults: NotificationSettings
    ) -> NotificationSettings:
        values: dict[str, Any] = {}
        if patch.on is not None:
            values["practice_on"] = patch.on
        if patch.at is not None:
            values["practice_at"] = patch.at
        return await self._upsert(account_id, values, defaults)

    async def patch_with_pause(
        self,
        account_id: UUID,
        columns: dict[str, object],
        defaults: NotificationSettings,
        today: date,
    ) -> tuple[NotificationSettings, PracticePause | None]:
        values: dict[str, Any] = {
            k: sorted(v) if k in _SORTED and isinstance(v, frozenset) else v  # pyright: ignore[reportUnknownArgumentType]
            for k, v in columns.items()
        }
        row = await self._upsert_row(account_id, values, _pause_columns(account_id, today))
        return _settings(row, defaults), _pause(row)

    async def _upsert(
        self, account_id: UUID, values: dict[str, Any], defaults: NotificationSettings
    ) -> NotificationSettings:
        return _settings(await self._upsert_row(account_id, values, ()), defaults)

    async def _upsert_row(
        self, account_id: UUID, values: dict[str, Any], extra: tuple[Label[Any], ...]
    ) -> Any:
        stmt = insert(_S).values(account_id=account_id, **values)
        returning = stmt.on_conflict_do_update(
            index_elements=[_S.c.account_id],
            set_={**{k: stmt.excluded[k] for k in values}, "updated_at": func.now()},
        ).returning(*_SETTINGS_COLUMNS, *extra)
        async with connection(self._engine) as conn:
            return (await conn.execute(returning)).one()

    async def candidates(
        self, since: datetime, logged_from: date, defaults: NotificationSettings
    ) -> list[ReminderCandidate]:
        """Reachable accounts with a known zone, a Telegram identity, and moon or practice
        reminders on."""
        moon_on = or_(_S.c.moon_offsets.is_(None), func.cardinality(_S.c.moon_offsets) > 0)
        if not defaults.moon.on:
            moon_on = func.cardinality(_S.c.moon_offsets) > 0
        reminders_on = or_(moon_on, _S.c.practice_on.is_(True))
        reachable = or_(_S.c.unreachable_at.is_(None), _S.c.unreachable_at < account.c.last_seen_at)
        accounts = (
            select(
                account.c.id,
                account.c.locale,
                account.c.timezone,
                account.c.moon_location,
                account.c.day_off,
                identity.c.provider_user_id,
                _S.c.moon_intro_sent_at,
                *_SETTINGS_COLUMNS,
            )
            .select_from(
                account.join(
                    identity,
                    and_(identity.c.account_id == account.c.id, identity.c.provider == "telegram"),
                ).outerjoin(_S, _S.c.account_id == account.c.id)
            )
            .where(account.c.timezone.is_not(None), reminders_on, reachable)
        )
        d = notification_delivery
        deliveries = select(
            d.c.account_id,
            d.c.dedupe_key,
            d.c.local_date,
            d.c.status,
            d.c.attempts,
            d.c.category,
            d.c.updated_at,
        ).where(d.c.created_at >= since)
        # Logged days, and (same statement, WH-01) the dates rest periods cover: practice
        # reminders skip both.
        logged_days = (
            select(
                day_log.c.account_id,
                day_log.c.local_date,
                false().label("paused"),
            )
            .join(_S, _S.c.account_id == day_log.c.account_id)
            .where(_S.c.practice_on.is_(True), day_log.c.local_date >= logged_from)
        )
        r = rest_period
        covered = (
            func.generate_series(
                func.greatest(r.c.start_date, logged_from),
                r.c.end_date,
                literal("1 day").cast(INTERVAL),
            )
            .table_valued("value")
            .render_derived("covered", with_types=False)
        )
        paused_days = (
            select(r.c.account_id, cast(covered.c.value, Date).label("local_date"), true())
            .select_from(r.join(_S, _S.c.account_id == r.c.account_id).join(covered, true()))
            .where(_S.c.practice_on.is_(True), r.c.end_date >= logged_from)
        )
        logged = union_all(logged_days, paused_days)
        async with connection(self._engine) as conn:
            rows = (await conn.execute(accounts)).all()
            recent = (await conn.execute(deliveries)).all()
            days = (await conn.execute(logged)).all()
        logged_by: dict[UUID, set[date]] = {}
        paused_by: dict[UUID, set[date]] = {}
        for r in days:
            (paused_by if r.paused else logged_by).setdefault(r.account_id, set()).add(r.local_date)
        by_account: dict[UUID, list[Delivery]] = {}
        stale_before = datetime.now(UTC) - STALE_CLAIM
        for r in recent:
            retryable = (r.status == "failed" and r.attempts < MAX_ATTEMPTS) or (
                r.status == "claimed" and r.updated_at < stale_before
            )
            by_account.setdefault(r.account_id, []).append(
                Delivery(r.dedupe_key, r.local_date, not retryable, r.status in ("sent", "claimed"))
            )
        out: list[ReminderCandidate] = []
        for r in rows:
            locale: Locale = r.locale if r.locale in LOCALES else DEFAULT_LOCALE
            out.append(
                ReminderCandidate(
                    account_id=r.id,
                    telegram_id=r.provider_user_id,
                    locale=locale,
                    zone=r.timezone,
                    location=r.moon_location,
                    settings=_settings(r, defaults_for(from_mask(r.day_off), defaults)),
                    deliveries=tuple(by_account.get(r.id, ())),
                    had_moon_reminder=r.moon_intro_sent_at is not None,
                    logged=frozenset(logged_by.get(r.id, ())),
                    paused=frozenset(paused_by.get(r.id, set[date]()) - logged_by.get(r.id, set())),
                )
            )
        return out

    async def claim(self, account_id: UUID, key: str, category: str, local_date: date) -> bool:
        d = notification_delivery
        stmt = insert(d).values(
            account_id=account_id,
            dedupe_key=key,
            category=category,
            local_date=local_date,
            status="claimed",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[d.c.account_id, d.c.dedupe_key],
            set_={"status": "claimed", "attempts": d.c.attempts + 1, "updated_at": func.now()},
            where=or_(
                and_(d.c.status == "failed", d.c.attempts < MAX_ATTEMPTS),
                and_(d.c.status == "claimed", d.c.updated_at < func.now() - STALE_CLAIM),
            ),
        ).returning(literal(1))
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).one_or_none() is not None

    async def finish(self, account_id: UUID, key: str, status: str) -> None:
        d = notification_delivery
        stmt = (
            update(d)
            .where(d.c.account_id == account_id, d.c.dedupe_key == key)
            .values(status=status, updated_at=func.now())
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def mark_unreachable(self, account_id: UUID, at: datetime) -> None:
        stmt = insert(_S).values(account_id=account_id, unreachable_at=at)
        stmt = stmt.on_conflict_do_update(
            index_elements=[_S.c.account_id], set_={"unreachable_at": at, "updated_at": func.now()}
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def prune(self, before: datetime) -> int:
        stmt = delete(notification_delivery).where(notification_delivery.c.created_at < before)
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).rowcount
