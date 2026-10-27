"""`DayLogRepository` on Postgres. A ladies' holiday is stored as 'rest' plus a sealed true
status on every rest row (ADR-0016); this adapter is the only place that knows."""

import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import and_, case, delete, exists, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import Label

from tristhana.application.ports.days import History, Inserted, RangeView, Upserted
from tristhana.domain.days import DayLog, DayStatus, public_status
from tristhana.domain.rest_periods import RestPeriod
from tristhana.infrastructure.crypto import UnreadableSeal
from tristhana.infrastructure.db.check_in import to_check_in
from tristhana.infrastructure.db.diary import note_arrays, open_notes
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.practice import to_practice
from tristhana.infrastructure.db.rest_periods import (
    cut_ctes,
    open_periods,
    period_arrays,
    practice_on_column,
)
from tristhana.infrastructure.db.tables import check_in, day_log, moon_day, practice

log = logging.getLogger(__name__)

# The sealed payload of a rest row: one byte, so rest and ladies seals have equal length.
_SEALED = {DayStatus.REST: b"r", DayStatus.LADIES: b"l"}
_UNSEALED = {v: k for k, v in _SEALED.items()}


class Cipher(Protocol):
    def seal(self, plaintext: bytes, aad: bytes) -> bytes: ...
    def open(self, sealed: bytes, aad: bytes) -> bytes: ...


def _aad(account_id: UUID, local_date: date) -> bytes:
    return b"day_log.sealed_status|" + account_id.bytes + local_date.isoformat().encode()


_practice_on = practice_on_column


def open_day_status(
    cipher: Cipher, account_id: UUID, local_date: date, sealed: bytes
) -> DayStatus | None:
    """A rest row's true value (rest or 🌸) for its owner; None = unreadable (ST-09)."""
    try:
        return _UNSEALED.get(cipher.open(bytes(sealed), _aad(account_id, local_date)))
    except UnreadableSeal:
        log.warning("unreadable day_log seal for account %s", account_id)
        return None


def _snapshot(account_id: UUID, when: date) -> tuple[Label[Any], ...]:
    """RETURNING columns read from the pre-statement snapshot (WH-01): the day before's
    status, the periods covering the day before or the day, practice reminders on."""
    before = and_(day_log.c.account_id == account_id, day_log.c.local_date == when - _DAY)
    return (
        select(day_log.c.status).where(before).scalar_subquery().label("prev_status"),
        select(day_log.c.sealed_status).where(before).scalar_subquery().label("prev_sealed"),
        *period_arrays(account_id, when - _DAY, when),
        _practice_on(account_id),
    )


_DAY = timedelta(days=1)


class SqlDayLogRepository:
    def __init__(self, engine: AsyncEngine, cipher: Cipher) -> None:
        self._engine = engine
        self._cipher = cipher

    async def upsert(self, account_id: UUID, day: DayLog, timezone: str | None) -> Upserted:
        public = public_status(day.status)
        sealed = (
            self._cipher.seal(_SEALED[day.status], _aad(account_id, day.local_date))
            if public is DayStatus.REST
            else None
        )
        values = {"status": public.value, "sealed_status": sealed, "timezone": timezone}
        stmt = insert(day_log).values(account_id=account_id, local_date=day.local_date, **values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[day_log.c.account_id, day_log.c.local_date],
            set_={**values, "updated_at": func.now()},
        )
        stale = delete(practice).where(
            practice.c.account_id == account_id, practice.c.local_date == day.local_date
        )
        stale_check_in = delete(check_in).where(
            check_in.c.account_id == account_id, check_in.c.local_date == day.local_date
        )
        if day.status is DayStatus.PRACTICED:
            # Details left over from a status change racing a save (or an old revision) go
            # when the day becomes practiced again; this snapshot still sees the old status.
            was_other = exists().where(
                day_log.c.account_id == account_id,
                day_log.c.local_date == day.local_date,
                day_log.c.status != "practiced",
            )
            stale, stale_check_in = stale.where(was_other), stale_check_in.where(was_other)
        # Same statement: a day that is no longer practiced loses its details (PR-02) and
        # its check-in (PR-06), and
        # 🧘 Practiced cuts a rest period covering the day (WH-01, ADR-0023), unless the day
        # was 🧘 already (a re-tap, e.g. after "keep the pause", cuts nothing).
        was_practiced = exists().where(
            day_log.c.account_id == account_id,
            day_log.c.local_date == day.local_date,
            day_log.c.status == "practiced",
        )
        stmt = stmt.add_cte(stale.cte("gone")).add_cte(stale_check_in.cte("gone_check_in"))
        for cte in cut_ctes(account_id, day.local_date, day.status, only_if=~was_practiced):
            stmt = stmt.add_cte(cte)
        stmt = stmt.returning(
            *_snapshot(account_id, day.local_date), was_practiced.label("was_practiced")
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        prev = (
            self._status(account_id, day.local_date - _DAY, row.prev_status, row.prev_sealed)
            if row.prev_status is not None
            else None
        )
        periods = open_periods(
            self._cipher, account_id, row.period_starts, row.period_ends, row.period_seals
        )
        return Upserted(
            day,
            prev=prev,
            periods=periods,
            practice_on=bool(row.practice_on),
            cut=None if row.was_practiced else _cut(periods, day),
        )

    async def insert_if_absent(
        self, account_id: UUID, day: DayLog, timezone: str | None
    ) -> Inserted:
        if day.status is DayStatus.LADIES:
            raise ValueError("reminder taps only log non-private statuses")
        sealed = (
            self._cipher.seal(_SEALED[day.status], _aad(account_id, day.local_date))
            if day.status is DayStatus.REST
            else None
        )
        stmt = (
            insert(day_log)
            .values(
                account_id=account_id,
                local_date=day.local_date,
                status=day.status.value,
                sealed_status=sealed,
                timezone=timezone,
            )
            .on_conflict_do_nothing(index_elements=[day_log.c.account_id, day_log.c.local_date])
            .returning(
                day_log.c.local_date, *period_arrays(account_id, day.local_date, day.local_date)
            )
        )
        # The cut applies only when the day is still empty (the snapshot before the insert).
        empty = ~exists().where(
            day_log.c.account_id == account_id, day_log.c.local_date == day.local_date
        )
        for cte in cut_ctes(account_id, day.local_date, day.status, only_if=empty):
            stmt = stmt.add_cte(cte)
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        if row is None:
            return Inserted(False)
        periods = open_periods(
            self._cipher, account_id, row.period_starts, row.period_ends, row.period_seals
        )
        return Inserted(True, _cut(periods, day))

    async def delete(self, account_id: UUID, local_date: date) -> None:
        stmt = delete(day_log).where(
            day_log.c.account_id == account_id, day_log.c.local_date == local_date
        )
        # Same statement: clearing a rest period's start day removes it (ADR-0023).
        for cte in cut_ctes(account_id, local_date, None):
            stmt = stmt.add_cte(cte)
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def list_range(self, account_id: UUID, start: date, end: date) -> list[DayLog]:
        async with connection(self._engine) as conn:
            rows = (await conn.execute(self._range(account_id, start, end))).all()
        return self._days(account_id, rows)

    async def range_with_moon(
        self, account_id: UUID, start: date, end: date, location: str
    ) -> RangeView:
        moon = (
            select(func.array_agg(moon_day.c.date).label("moon_dates"))
            .where(moon_day.c.location == location, moon_day.c.date.between(start, end))
            .subquery("moon")
        )
        days = self._range(account_id, start, end).subquery("days")
        # The notes (up to 8 KB each) ride on the first row only, not on every (day, slot) row.
        first = func.row_number().over(order_by=(days.c.local_date, days.c.slot)) == 1
        note_dates, note_seals = note_arrays(account_id, start, end)
        # One row even when nothing is logged: the moon dates always come back (as `history`).
        stmt = (
            select(
                moon.c.moon_dates,
                *period_arrays(account_id, start, end),
                case((first, note_dates), else_=None).label("note_dates"),  # PR-07
                case((first, note_seals), else_=None).label("note_seals"),
                _practice_on(account_id),
                *days.c,
            )
            .select_from(moon.outerjoin(days, literal(True)))
            .order_by(days.c.local_date, days.c.slot)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        moon_dates = frozenset(rows[0].moon_dates or ()) if rows else frozenset[date]()
        return RangeView(
            self._days(account_id, [r for r in rows if r.local_date is not None]),
            moon_dates,
            self._periods(account_id, rows),
            bool(rows[0].practice_on) if rows else False,
            open_notes(self._cipher, account_id, rows[0].note_dates, rows[0].note_seals)
            if rows
            else {},
        )

    async def history(self, account_id: UUID, start: date, end: date) -> History:
        first = (
            select(func.min(day_log.c.local_date).label("first_date"))
            .where(day_log.c.account_id == account_id)
            .subquery("first")
        )
        days = self._range(account_id, start, end).subquery("days")
        # One row even when the range is empty: the first date always comes back.
        stmt = (
            select(first.c.first_date, *period_arrays(account_id, start, end), *days.c)
            .select_from(first.outerjoin(days, literal(True)))
            .order_by(days.c.local_date, days.c.slot)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        first_date = rows[0].first_date if rows else None
        return History(
            self._days(account_id, [r for r in rows if r.local_date is not None]),
            first_date,
            self._periods(account_id, rows),
        )

    def _periods(self, account_id: UUID, rows: Sequence[Any]) -> tuple[RestPeriod, ...]:
        if not rows:
            return ()
        r = rows[0]
        return open_periods(
            self._cipher, account_id, r.period_starts, r.period_ends, r.period_seals
        )

    def _range(self, account_id: UUID, start: date, end: date) -> Any:  # a Select
        return (
            select(
                day_log.c.local_date,
                day_log.c.status,
                day_log.c.sealed_status,
                practice.c.slot,
                practice.c.context,
                practice.c.online,
                practice.c.series,
                practice.c.end_item,
                practice.c.first_part,
                practice.c.duration_min,
                practice.c.start_time,
                practice.c.timezone,
                check_in.c.slot.label("check_in_slot"),
                check_in.c.mood,
                check_in.c.energy,
                check_in.c.effort,
                check_in.c.tags,
            )
            .select_from(
                day_log.outerjoin(
                    practice,
                    and_(
                        practice.c.account_id == day_log.c.account_id,
                        practice.c.local_date == day_log.c.local_date,
                        # Also hides a row left by a rare status/details race.
                        day_log.c.status == "practiced",
                    ),
                ).outerjoin(
                    check_in,
                    and_(
                        check_in.c.account_id == day_log.c.account_id,
                        check_in.c.local_date == day_log.c.local_date,
                        day_log.c.status == "practiced",
                    ),
                )
            )
            .where(
                day_log.c.account_id == account_id,
                day_log.c.local_date.between(start, end),
            )
            .order_by(day_log.c.local_date, practice.c.slot)
        )

    def _days(self, account_id: UUID, rows: Sequence[Any]) -> list[DayLog]:
        days: dict[date, DayLog] = {}
        for row in rows:
            day = days.get(row.local_date) or DayLog(
                row.local_date,
                self._status(account_id, row.local_date, row.status, row.sealed_status),
            )
            if row.slot is not None:
                day = replace(day, practices=(*day.practices, to_practice(row)))
            if row.check_in_slot is not None and not day.check_ins:
                found = to_check_in(row)
                if not found.is_empty():  # an empty row reads as no check-in
                    day = replace(day, check_ins=(found,))
            days[row.local_date] = day
        return list(days.values())

    def _status(
        self, account_id: UUID, local_date: date, status: str, sealed: bytes | None
    ) -> DayStatus:
        if sealed is None:
            return DayStatus(status)
        try:
            return _UNSEALED.get(
                self._cipher.open(sealed, _aad(account_id, local_date)), DayStatus.REST
            )
        except UnreadableSeal:
            # Lost or retired key: only the rest/ladies distinction is lost, never the day.
            log.warning("unreadable day_log seal for account %s", account_id)
            return DayStatus.REST


def _cut(periods: Sequence[RestPeriod], day: DayLog) -> RestPeriod | None:
    """The period as it was before a 🧘 Practiced on `day` cut it (for "keep the pause")."""
    if day.status is not DayStatus.PRACTICED:
        return None
    return next((p for p in periods if p.covers(day.local_date)), None)
