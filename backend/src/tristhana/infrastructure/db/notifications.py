"""Notification settings and the delivery ledger (MD-03, ADR-0018)."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.notifications import Delivery, MoonCandidate, MoonPatch
from tristhana.domain.locale import DEFAULT_LOCALE, LOCALES, Locale
from tristhana.domain.notifications import (
    MoonReminders,
    NotificationSettings,
    QuietHours,
)
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import (
    account,
    identity,
    notification_delivery,
    notification_settings,
)

MAX_ATTEMPTS = 3
# A claim older than this was cut off mid-send (a tick past its deadline): take it over.
STALE_CLAIM = timedelta(minutes=5)
_S = notification_settings


def _settings(row: Any, defaults: NotificationSettings) -> NotificationSettings:
    """A stored row (or None) over the defaults: NULL columns mean "the default"."""
    if row is None:
        return defaults
    offsets = frozenset(row.moon_offsets) if row.moon_offsets is not None else defaults.moon.offsets
    return NotificationSettings(
        moon=MoonReminders(offsets, row.moon_at or defaults.moon.at),
        quiet=QuietHours(
            row.quiet_start or defaults.quiet.start, row.quiet_end or defaults.quiet.end
        )
        if row.quiet_start is not None or row.quiet_end is not None
        else defaults.quiet,
        daily_cap=row.daily_cap or defaults.daily_cap,
    )


_SETTINGS_COLUMNS = (
    _S.c.moon_offsets,
    _S.c.moon_at,
    _S.c.quiet_start,
    _S.c.quiet_end,
    _S.c.daily_cap,
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

    async def save(self, account_id: UUID, settings: NotificationSettings) -> NotificationSettings:
        values = {
            "moon_offsets": sorted(settings.moon.offsets),
            "moon_at": settings.moon.at,
            "quiet_start": settings.quiet.start,
            "quiet_end": settings.quiet.end,
            "daily_cap": settings.daily_cap,
        }
        return await self._upsert(account_id, values, settings)

    async def patch_moon(
        self, account_id: UUID, patch: MoonPatch, defaults: NotificationSettings
    ) -> NotificationSettings:
        values: dict[str, Any] = {}
        if patch.offsets is not None:
            values["moon_offsets"] = sorted(patch.offsets)
        if patch.at is not None:
            values["moon_at"] = patch.at
        return await self._upsert(account_id, values, defaults)

    async def _upsert(
        self, account_id: UUID, values: dict[str, Any], defaults: NotificationSettings
    ) -> NotificationSettings:
        stmt = insert(_S).values(account_id=account_id, **values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[_S.c.account_id],
            set_={**{k: stmt.excluded[k] for k in values}, "updated_at": func.now()},
        ).returning(*_SETTINGS_COLUMNS)
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return _settings(row, defaults)

    async def moon_candidates(
        self, since: datetime, defaults: NotificationSettings
    ) -> list[MoonCandidate]:
        """Reachable accounts with a known zone, a Telegram identity and moon reminders on."""
        reminders_on = or_(_S.c.moon_offsets.is_(None), func.cardinality(_S.c.moon_offsets) > 0)
        if not defaults.moon.on:
            reminders_on = func.cardinality(_S.c.moon_offsets) > 0
        reachable = or_(_S.c.unreachable_at.is_(None), _S.c.unreachable_at < account.c.last_seen_at)
        accounts = (
            select(
                account.c.id,
                account.c.locale,
                account.c.timezone,
                account.c.moon_location,
                identity.c.provider_user_id,
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
        ever = select(d.c.account_id).where(d.c.category == "moon", d.c.status == "sent").distinct()
        async with connection(self._engine) as conn:
            rows = (await conn.execute(accounts)).all()
            recent = (await conn.execute(deliveries)).all()
            had = {r.account_id for r in (await conn.execute(ever)).all()}
        by_account: dict[UUID, list[Delivery]] = {}
        stale_before = datetime.now(UTC) - STALE_CLAIM
        for r in recent:
            retryable = (r.status == "failed" and r.attempts < MAX_ATTEMPTS) or (
                r.status == "claimed" and r.updated_at < stale_before
            )
            by_account.setdefault(r.account_id, []).append(
                Delivery(r.dedupe_key, r.local_date, not retryable, r.status in ("sent", "claimed"))
            )
        out: list[MoonCandidate] = []
        for r in rows:
            locale: Locale = r.locale if r.locale in LOCALES else DEFAULT_LOCALE
            out.append(
                MoonCandidate(
                    account_id=r.id,
                    telegram_id=r.provider_user_id,
                    locale=locale,
                    zone=r.timezone,
                    location=r.moon_location,
                    settings=_settings(r, defaults),
                    deliveries=tuple(by_account.get(r.id, ())),
                    had_moon_reminder=r.id in had,
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
