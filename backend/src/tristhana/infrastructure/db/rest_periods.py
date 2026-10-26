"""`RestPeriodRepository` on Postgres (WH-01 part 2, ADR-0023). The kind is sealed on every
row (`l`/`k`/`t`, one byte, the ADR-0016 format), so a 🌸 period looks like a sick or
travel one; this module is the only place that knows. The overlap rule
(`domain.rest_periods.place`) and the cut by a log (`cut_by_log`, used by `db/days.py`)
run as CTEs in the same statement as the write."""

import logging
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import (
    Date,
    LargeBinary,
    Uuid,
    and_,
    delete,
    exists,
    false,
    func,
    literal,
    select,
    true,
    union_all,
    update,
)
from sqlalchemy.dialects.postgresql import aggregate_order_by, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import Label

from tristhana.application.ports.rest_periods import Ended, Placed
from tristhana.domain.days import DayStatus
from tristhana.domain.rest_periods import MAX_PERIOD_DAYS, RestPeriod
from tristhana.infrastructure.crypto import UnreadableSeal
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import day_log, notification_settings, rest_period

log = logging.getLogger(__name__)

_SEALED = {DayStatus.LADIES: b"l", DayStatus.SICK: b"k", DayStatus.TRAVEL: b"t"}
_UNSEALED = {v: k for k, v in _SEALED.items()}
_DAY = timedelta(days=1)
_R = rest_period


class Cipher(Protocol):
    def seal(self, plaintext: bytes, aad: bytes) -> bytes: ...
    def open(self, sealed: bytes, aad: bytes) -> bytes: ...


def _aad(account_id: UUID, start: date) -> bytes:
    return b"rest_period.sealed_kind|" + account_id.bytes + start.isoformat().encode()


def seal_kind(cipher: Cipher, account_id: UUID, period: RestPeriod) -> bytes:
    return cipher.seal(_SEALED[period.kind], _aad(account_id, period.start))


def open_period(
    cipher: Cipher, account_id: UUID, start: date, end: date, sealed: bytes
) -> RestPeriod:
    """Unreadable (lost key, a seal moved to another row): plain rest, never the dates
    lost. The warning names the account only, never the kind or the dates."""
    try:
        kind = _UNSEALED.get(cipher.open(sealed, _aad(account_id, start)), DayStatus.REST)
    except UnreadableSeal:
        log.warning("unreadable rest_period seal for account %s", account_id)
        kind = DayStatus.REST
    return RestPeriod(start, end, kind)


def open_periods(
    cipher: Cipher,
    account_id: UUID,
    starts: Sequence[date] | None,
    ends: Sequence[date] | None,
    seals: Sequence[bytes] | None,
) -> tuple[RestPeriod, ...]:
    """From the three arrays of `period_arrays` (NULL when there is none)."""
    if not starts or not ends or not seals:
        return ()
    return tuple(
        open_period(cipher, account_id, s, e, k)
        for s, e, k in zip(starts, ends, seals, strict=True)
    )


def period_arrays(
    account_id: UUID, start: date, end: date
) -> tuple[Label[Any], Label[Any], Label[Any]]:
    """Scalar subqueries: the periods overlapping [start, end] as three arrays ordered by
    start (`period_starts`, `period_ends`, `period_seals`). A PK range thanks to the cap."""
    window = and_(
        _R.c.account_id == account_id,
        _R.c.start_date.between(start - timedelta(days=MAX_PERIOD_DAYS - 1), end),
        _R.c.end_date >= start,
    )

    def agg(column: Any, label: str) -> Label[Any]:
        return (
            select(func.array_agg(aggregate_order_by(column, _R.c.start_date)))
            .where(window)
            .scalar_subquery()
            .label(label)
        )

    return (
        agg(_R.c.start_date, "period_starts"),
        agg(_R.c.end_date, "period_ends"),
        agg(_R.c.sealed_kind, "period_seals"),
    )


def cut_ctes(
    account_id: UUID, day: date, status: DayStatus | None, only_if: Any = None
) -> list[Any]:
    """`cut_by_log` as data-modifying CTEs for a log (or a clear, `status` None) on `day`:
    🧘 Practiced ends the period covering it the day before (removed when only its start
    is left); clearing its start day removes it; anything else changes nothing."""
    if status is None:
        gone = delete(_R).where(_R.c.account_id == account_id, _R.c.start_date == day)
        return [gone.cte("period_cleared")]
    if status is not DayStatus.PRACTICED:
        return []
    covering = and_(
        _R.c.account_id == account_id,
        _R.c.start_date.between(day - timedelta(days=MAX_PERIOD_DAYS - 1), day),
        _R.c.end_date >= day,
    )
    if only_if is not None:
        covering = and_(covering, only_if)
    shorten = (
        update(_R)
        .where(covering, _R.c.start_date < day - _DAY)
        .values(end_date=day - _DAY, updated_at=func.now())
    )
    remove = delete(_R).where(covering, _R.c.start_date >= day - _DAY)
    return [shorten.cte("period_cut"), remove.cte("period_cut_gone")]


def practice_on_column(account_id: UUID) -> Label[Any]:
    """Scalar subquery: practice reminders on (labels on covered days, the pause wording)."""
    n = notification_settings
    on = select(n.c.practice_on).where(n.c.account_id == account_id).scalar_subquery()
    return func.coalesce(on, false()).label("practice_on")


# `pg_advisory_xact_lock(key, account)`: writes that place a period run one at a time per
# account, so two taps at once can't both miss each other's period (coverage never overlaps).
_LOCK_KEY = 0x52504552  # "RPER"


def _lock_id(account_id: UUID) -> int:
    return int.from_bytes(account_id.bytes[:4], "big", signed=True)


class SqlRestPeriodRepository:
    def __init__(self, engine: AsyncEngine, cipher: Cipher) -> None:
        self._engine = engine
        self._cipher = cipher

    async def place(self, account_id: UUID, period: RestPeriod) -> Placed:
        stmt = self._placing(account_id, period, gate=None).returning(
            practice_on_column(account_id)
        )
        row = await self._locked(account_id, stmt)
        return Placed(period, bool(row is not None and row.practice_on))

    async def restore(self, account_id: UUID, period: RestPeriod, today: date) -> RestPeriod | None:
        # A cut happened: a 🧘 day inside what is kept (else a forged keep could backfill).
        gate = exists().where(
            day_log.c.account_id == account_id,
            day_log.c.local_date.between(period.start, min(period.end, today)),
            day_log.c.status == DayStatus.PRACTICED.value,
        )
        stmt = self._placing(account_id, period, gate).returning(_R.c.start_date)
        row = await self._locked(account_id, stmt)
        return period if row is not None else None

    async def _locked(self, account_id: UUID, stmt: Any) -> Any:
        """The lock and the write in one transaction (the write's snapshot is taken after
        the lock is held)."""
        lock = select(func.pg_advisory_xact_lock(_LOCK_KEY, _lock_id(account_id)))
        async with connection(self._engine) as conn:
            conn = await conn.execution_options(isolation_level="READ COMMITTED")
            async with conn.begin():
                await conn.execute(lock)
                return (await conn.execute(stmt)).one_or_none()

    def _placing(self, account_id: UUID, period: RestPeriod, gate: Any) -> Any:
        """INSERT … ON CONFLICT DO UPDATE with the overlap rule as CTEs; with `gate`, the
        insert and both CTEs apply only when it holds (all or nothing, one statement)."""
        start, end = period.start, period.end
        mine = _R.c.account_id == account_id
        if gate is not None:
            mine = and_(mine, gate)
        earlier = and_(mine, _R.c.start_date < start, _R.c.end_date >= start)
        # An earlier period covering `start` ends the day before, or goes when only its
        # start day would be left; periods starting inside the new one go. One on `start`
        # itself is replaced by the upsert below (never touched by the CTEs).
        ended = (
            update(_R)
            .where(earlier, _R.c.start_date < start - _DAY)
            .values(end_date=start - _DAY, updated_at=func.now())
        )
        gone = delete(_R).where(
            mine,
            (_R.c.start_date.between(start + _DAY, end))
            | and_(earlier, _R.c.start_date >= start - _DAY),
        )
        sealed = seal_kind(self._cipher, account_id, period)
        values = select(
            literal(account_id, Uuid()).label("account_id"),
            literal(start, Date()).label("start_date"),
            literal(end, Date()).label("end_date"),
            literal(sealed, LargeBinary()).label("sealed_kind"),
        )
        if gate is not None:
            values = values.where(gate)
        stmt = insert(_R).from_select(
            ["account_id", "start_date", "end_date", "sealed_kind"], values
        )
        return (
            stmt.on_conflict_do_update(
                index_elements=[_R.c.account_id, _R.c.start_date],
                set_={
                    "end_date": stmt.excluded.end_date,
                    "sealed_kind": stmt.excluded.sealed_kind,
                    "updated_at": func.now(),
                },
            )
            .add_cte(ended.cte("period_ended"))
            .add_cte(gone.cte("period_gone"))
        )

    async def end(self, account_id: UUID, start: date, today: date) -> Ended:
        this = and_(_R.c.account_id == account_id, _R.c.start_date == start)
        running = and_(this, _R.c.end_date >= today)
        # `end_from`: stops covering today; removed when ≤ 1 day is left; untouched if over.
        # Every branch returns the row (the removed one too: its kind names what ended).
        columns = (_R.c.start_date, _R.c.end_date, _R.c.sealed_kind)
        gone = (
            delete(_R)
            .where(running, _R.c.start_date >= today - _DAY)
            .returning(*columns)
            .cte("period_end_gone")
        )
        cut = (
            update(_R)
            .where(running, _R.c.start_date < today - _DAY)
            .values(end_date=today - _DAY, updated_at=func.now())
            .returning(*columns)
            .cte("period_end_cut")
        )
        stmt = union_all(
            select(cut.c.start_date, cut.c.end_date, cut.c.sealed_kind, false().label("gone")),
            select(gone.c.start_date, gone.c.end_date, gone.c.sealed_kind, true().label("gone")),
            select(*columns, false().label("gone")).where(this, _R.c.end_date < today),
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).first()
        if row is None:
            return Ended(None)
        period = open_period(self._cipher, account_id, row[0], row[1], row[2])
        return Ended(None if row[3] else period, period.kind)
