"""`ListingRepository` on Postgres (ID-05, ADR-0042). `save` and `decide` are one short
transaction each (lock, read, write): rare writes where a lost race would show a teacher a
line the checker never saw. Names, regions and notes are never logged.

`mark_columns` / `to_mark` are the one way a listing crosses accounts: a LEFT JOIN on the
teacher's id inside statements that already load the teacher's name (ID-04).
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, literal, select, text, true, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.directory_listing import (
    PAGE,
    Decided,
    RequestCard,
    RequestRow,
    RequestsPage,
    Saved,
)
from tristhana.application.ports.notifications import Recipient
from tristhana.domain.directory_listing import (
    DeclaredLevel,
    Details,
    Listing,
    ListingMark,
    ListingStatus,
    Outcome,
    Step,
    may_decide,
)
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import account, directory_listing, identity

_L = directory_listing
LISTING_COLUMNS = _COLUMNS = (
    _L.c.status,
    _L.c.name_as_listed,
    _L.c.region,
    _L.c.declared_level,
    _L.c.note,
    _L.c.revision,
    _L.c.requested_at,
    _L.c.checked_on,
)
MARK_COLUMNS = (
    _L.c.name_as_listed.label("listing_name"),
    _L.c.checked_on.label("listing_checked_on"),
    _L.c.declared_level.label("listing_level"),
)


def mark_join(teacher: Any) -> Any:
    """The ON clause of the LEFT JOIN: the teacher's row, only while listed."""
    return and_(_L.c.account_id == teacher, _L.c.status == ListingStatus.LISTED.value)


def to_mark(row: Any) -> ListingMark | None:
    if row.listing_name is None or row.listing_checked_on is None:
        return None
    level = DeclaredLevel(row.listing_level) if row.listing_level else None
    return ListingMark(row.listing_name, row.listing_checked_on, level)


def to_listing(row: Any) -> Listing:
    return Listing(
        status=ListingStatus(row.status),
        name_as_listed=row.name_as_listed,
        region=row.region,
        level=DeclaredLevel(row.declared_level) if row.declared_level else None,
        note=row.note,
        revision=row.revision,
        requested_at=row.requested_at,
        checked_on=row.checked_on,
    )


class SqlListingRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, me: UUID) -> Listing | None:
        async with connection(self._engine) as conn:
            row = (await conn.execute(select(*_COLUMNS).where(_L.c.account_id == me))).one_or_none()
        return to_listing(row) if row else None

    async def save(
        self,
        me: UUID,
        details: Details,
        plan: Callable[[Listing | None], Step],
        now: datetime,
    ) -> Saved:
        level = details.level.value if details.level else None
        async with connection(self._engine) as conn:
            conn = await conn.execution_options(isolation_level="READ COMMITTED")
            async with conn.begin():
                # No row to lock on a first send: a transaction-scoped advisory lock on the
                # account serialises two taps (and a decide's row lock waits for the write).
                await conn.execute(
                    select(func.pg_advisory_xact_lock(func.hashtextextended(str(me), 0)))
                )
                found = (
                    await conn.execute(
                        select(*_COLUMNS).where(_L.c.account_id == me).with_for_update()
                    )
                ).one_or_none()
                step = plan(to_listing(found) if found else None)  # may raise: nothing written
                if step is Step.LEVEL_ONLY:
                    stmt = (
                        update(_L)
                        .where(_L.c.account_id == me)
                        .values(declared_level=level, revision=_L.c.revision + 1)
                        .returning(*_COLUMNS)
                    )
                else:
                    fresh = step in (Step.SEND, Step.RECHECK)
                    values: dict[str, Any] = {
                        "status": ListingStatus.PENDING.value,
                        "name_as_listed": details.name_as_listed,
                        "region": details.region,
                        "declared_level": level,
                        "note": details.note,
                        "checked_on": None,
                        "checked_by": None,
                        "decided_at": None,
                    }
                    changed = values | {"revision": _L.c.revision + 1}
                    if fresh:
                        changed["requested_at"] = now
                    stmt = (
                        insert(_L)
                        .values(account_id=me, requested_at=now, **values)
                        .on_conflict_do_update(index_elements=[_L.c.account_id], set_=changed)
                        .returning(*_COLUMNS)
                    )
                row = (await conn.execute(stmt)).one()
        return Saved(to_listing(row), step)

    async def withdraw(self, me: UUID) -> None:
        stmt = (
            update(_L)
            .where(_L.c.account_id == me, _L.c.status != ListingStatus.WITHDRAWN.value)
            .values(
                status=ListingStatus.WITHDRAWN.value,
                name_as_listed=None,
                region=None,
                declared_level=None,
                note=None,
                checked_on=None,
                checked_by=None,
                revision=_L.c.revision + 1,
            )
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def recipients(self, accounts: frozenset[UUID]) -> tuple[Recipient, ...]:
        if not accounts:
            return ()
        stmt = (
            select(identity.c.provider_user_id, account.c.locale)
            .join_from(identity, account, account.c.id == identity.c.account_id)
            .where(identity.c.account_id.in_(accounts), identity.c.provider == "telegram")
            .order_by(identity.c.account_id)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        return tuple(Recipient(r.provider_user_id, r.locale) for r in rows)

    async def requests(self, listed: bool, page: int) -> RequestsPage:
        """One statement: the counts always come back, with or without rows on this page."""
        pending = _L.c.status == ListingStatus.PENDING.value
        shown = _L.c.status == ListingStatus.LISTED.value
        counts = select(
            func.count().filter(pending).label("waiting"),
            func.count().filter(shown).label("listed"),
            func.min(_L.c.checked_on).filter(shown).label("oldest"),
        ).subquery("counts")
        at = _L.c.checked_on if listed else func.date(func.timezone("UTC", _L.c.requested_at))
        order = (
            (_L.c.checked_on, _L.c.account_id)
            if listed
            else (
                _L.c.requested_at,
                _L.c.account_id,
            )
        )
        rows = (
            select(_L.c.account_id, _L.c.name_as_listed, at.label("at"))
            .where(shown if listed else pending)
            .order_by(*order)
            .limit(PAGE)
            .offset(page * PAGE)
            .subquery("rows")
        )
        stmt = select(counts, rows).select_from(counts.outerjoin(rows, true()))
        async with connection(self._engine) as conn:
            found = (await conn.execute(stmt)).all()
        first = found[0]
        return RequestsPage(
            rows=tuple(
                RequestRow(r.account_id, r.name_as_listed, r.at)
                for r in found
                if r.account_id is not None
            ),
            waiting=first.waiting,
            listed=first.listed,
            oldest_check=first.oldest,
        )

    async def request(self, account_id: UUID) -> RequestCard | None:
        stmt = (
            select(account.c.display_name, *_COLUMNS)
            .join_from(_L, account, account.c.id == _L.c.account_id)
            .where(_L.c.account_id == account_id, _L.c.status != ListingStatus.WITHDRAWN.value)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        if row is None:
            return None
        return RequestCard(account_id, row.display_name, to_listing(row))

    async def decide(
        self,
        account_id: UUID,
        revision: int,
        outcome: Outcome,
        checked_on: date,
        by: UUID,
    ) -> Decided | None:
        listed = outcome is Outcome.LISTED
        telegram = and_(identity.c.account_id == _L.c.account_id, identity.c.provider == "telegram")
        read = (
            select(*_COLUMNS, account.c.locale, identity.c.provider_user_id)
            .select_from(
                _L.join(account, account.c.id == _L.c.account_id).outerjoin(identity, telegram)
            )
            .where(_L.c.account_id == account_id, _L.c.revision == revision)
            .with_for_update(of=_L)
        )
        write = (
            update(_L)
            .where(_L.c.account_id == account_id)
            .values(
                status=(ListingStatus.LISTED if listed else ListingStatus.NOT_FOUND).value,
                note=None,
                revision=_L.c.revision + 1,
                checked_on=literal(checked_on) if listed else None,
                checked_by=by,
                decided_at=text("now()"),
            )
        )
        async with connection(self._engine) as conn:
            conn = await conn.execution_options(isolation_level="READ COMMITTED")
            async with conn.begin():
                row = (await conn.execute(read)).first()
                if row is None:
                    return None
                current = to_listing(row)
                if not may_decide(current) or current.name_as_listed is None:
                    return None
                await conn.execute(write)
        teacher = Recipient(row.provider_user_id, row.locale) if row.provider_user_id else None
        return Decided(teacher, current.name_as_listed, current.status is ListingStatus.LISTED)
