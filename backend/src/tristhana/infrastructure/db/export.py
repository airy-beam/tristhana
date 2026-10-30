"""`ExportRepository` on Postgres (ST-09, ADR-0027): every row of one account in one read-only
REPEATABLE READ transaction (PK-range reads), seals opened for the owner with the same AADs
the writers use; and the 10-minute export slot on `account.export_claimed_at`."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.export import Owned
from tristhana.domain.check_in import CheckIn
from tristhana.domain.days import DayStatus
from tristhana.domain.export import (
    ExportCheckIn,
    ExportDay,
    ExportEvent,
    ExportIdentity,
    ExportMilestone,
    ExportNote,
    ExportPeriod,
    ExportPractice,
    ExportReminder,
    MarkedBy,
)
from tristhana.domain.notifications import NotificationSettings
from tristhana.domain.progression import EventKind, Position, Progression, ProgressionEvent
from tristhana.infrastructure.db.accounts import ACCOUNT_COLUMNS, to_account
from tristhana.infrastructure.db.check_in import known_tags
from tristhana.infrastructure.db.days import Cipher, open_day_status
from tristhana.infrastructure.db.diary import open_note
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.notifications import settings_over
from tristhana.infrastructure.db.practice import to_practice
from tristhana.infrastructure.db.rest_periods import open_kind
from tristhana.infrastructure.db.tables import (
    account,
    check_in,
    day_log,
    diary_note,
    identity,
    notification_delivery,
    notification_settings,
    practice,
    practice_milestone,
    progression,
    progression_event,
    rest_period,
)

# Tables with an FK to `account.id`: each is exported or excluded on purpose. A test fails
# when a new table is in neither list (Phase 3 tables must choose).
EXPORTED_TABLES = frozenset(
    {
        "identity",
        "day_log",
        "rest_period",
        "practice",
        "check_in",
        "diary_note",
        "progression",
        "progression_event",
        "notification_settings",
        "notification_delivery",  # as `reminders` (category, date, status; 60 days)
        "practice_milestone",  # as `practice_milestones` (GM-01 part 2)
    }
)
EXCLUDED_TABLES: dict[str, str] = {}  # table -> why it isn't exported


class SqlExportRepository:
    def __init__(self, engine: AsyncEngine, cipher: Cipher) -> None:
        self._engine = engine
        self._cipher = cipher

    async def snapshot(
        self, account_id: UUID, defaults: NotificationSettings, reminders_from: date
    ) -> Owned | None:
        async with connection(self._engine) as conn:
            conn = await conn.execution_options(
                isolation_level="REPEATABLE READ", postgresql_readonly=True
            )
            async with conn.begin():
                row = (
                    await conn.execute(select(*ACCOUNT_COLUMNS).where(account.c.id == account_id))
                ).one_or_none()
                if row is None:
                    return None
                rows = [
                    (await conn.execute(stmt)).all()
                    for stmt in _statements(account_id, reminders_from)
                ]
        ids, settings, days, periods, practices, check_ins, notes, state, events, sent, passed = (
            rows
        )
        return Owned(
            account=to_account(row),
            identities=tuple(
                ExportIdentity(r.provider, r.provider_user_id, r.created_at) for r in ids
            ),
            settings=settings_over(settings[0] if settings else None, defaults),
            days=tuple(self._day(account_id, r) for r in days),
            periods=tuple(
                ExportPeriod(
                    r.start_date,
                    r.end_date,
                    open_kind(self._cipher, account_id, r.start_date, r.sealed_kind),
                )
                for r in periods
            ),
            practices=tuple(ExportPractice(r.local_date, to_practice(r)) for r in practices),
            check_ins=tuple(
                ExportCheckIn(
                    r.local_date,
                    CheckIn(r.mood, r.energy, r.effort, known_tags(r.tags), r.slot),
                )
                for r in check_ins
            ),
            notes=tuple(
                ExportNote(
                    r.local_date,
                    open_note(self._cipher, account_id, r.local_date, r.sealed_text).text,
                )
                for r in notes
            ),
            progression=(
                Progression(Position(state[0].series, state[0].last_key), frozenset(state[0].items))
                if state
                else None
            ),
            events=tuple(_event(account_id, r) for r in events),
            reminders=tuple(ExportReminder(r.category, r.local_date, r.status) for r in sent),
            milestones=tuple(
                ExportMilestone(r.threshold, r.reached_at, r.celebrated) for r in passed
            ),
        )

    async def claim(self, account_id: UUID, now: datetime, before: datetime) -> datetime | None:
        """READ COMMITTED: a concurrent claim waits on the row lock and then re-checks the
        WHERE, so exactly one wins. The loser's `earlier` comes from its statement snapshot,
        so it may be stale (the use case then applies the whole window)."""
        a = account
        earlier = select(a.c.export_claimed_at).where(a.c.id == account_id).cte("earlier")
        claimed = (
            update(a)
            .where(
                a.c.id == account_id,
                or_(a.c.export_claimed_at.is_(None), a.c.export_claimed_at <= before),
            )
            .values(export_claimed_at=now)
            .returning(literal(1).label("one"))
            .cte("claimed")
        )
        stmt = select(
            exists(select(claimed.c.one)).label("claimed"),
            select(earlier.c.export_claimed_at).scalar_subquery().label("earlier"),
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        if row.claimed:
            return None
        return row.earlier or now  # None: a claim landed after our snapshot

    async def release(self, account_id: UUID) -> None:
        stmt = update(account).where(account.c.id == account_id).values(export_claimed_at=None)
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    def _day(self, account_id: UUID, r: Any) -> ExportDay:
        if r.sealed_status is None:
            return ExportDay(r.local_date, DayStatus(r.status), r.timezone)
        opened = open_day_status(self._cipher, account_id, r.local_date, r.sealed_status)
        if opened is None:  # never guessed: plain rest, marked unreadable
            return ExportDay(r.local_date, DayStatus.REST, r.timezone, unreadable=True)
        return ExportDay(r.local_date, opened, r.timezone)


def _statements(account_id: UUID, reminders_from: date) -> list[Any]:
    """In `snapshot`'s unpacking order; each a PK (or index) range of this account only."""
    return [
        select(identity.c.provider, identity.c.provider_user_id, identity.c.created_at)
        .where(identity.c.account_id == account_id)
        .order_by(identity.c.created_at),
        select(notification_settings).where(notification_settings.c.account_id == account_id),
        select(day_log.c.local_date, day_log.c.status, day_log.c.sealed_status, day_log.c.timezone)
        .where(day_log.c.account_id == account_id)
        .order_by(day_log.c.local_date),
        select(rest_period.c.start_date, rest_period.c.end_date, rest_period.c.sealed_kind)
        .where(rest_period.c.account_id == account_id)
        .order_by(rest_period.c.start_date),
        select(practice)
        .where(practice.c.account_id == account_id)
        .order_by(practice.c.local_date, practice.c.slot),
        select(check_in)
        .where(check_in.c.account_id == account_id)
        .order_by(check_in.c.local_date, check_in.c.slot),
        select(diary_note.c.local_date, diary_note.c.sealed_text)
        .where(diary_note.c.account_id == account_id)
        .order_by(diary_note.c.local_date),
        select(progression).where(progression.c.account_id == account_id),
        select(progression_event)
        .where(progression_event.c.account_id == account_id)
        .order_by(progression_event.c.id),
        select(
            notification_delivery.c.category,
            notification_delivery.c.local_date,
            notification_delivery.c.status,
        )
        .where(
            and_(
                notification_delivery.c.account_id == account_id,
                notification_delivery.c.local_date >= reminders_from,
            )
        )
        .order_by(notification_delivery.c.local_date, notification_delivery.c.category),
        select(
            practice_milestone.c.threshold,
            practice_milestone.c.reached_at,
            practice_milestone.c.celebrated,
        )
        .where(practice_milestone.c.account_id == account_id)
        .order_by(practice_milestone.c.threshold),
    ]


def _event(account_id: UUID, r: Any) -> ExportEvent:
    kind = EventKind(r.kind)
    positional = kind not in (EventKind.ITEM_GIVEN, EventKind.ITEM_REMOVED)
    before = Position(r.from_series, r.from_key) if positional else None
    event = ProgressionEvent(
        id=r.id,
        kind=kind,
        occurred_on=r.occurred_on,
        before=None if kind is EventKind.START else before,
        after=Position(r.to_series, r.to_key) if positional else None,
        item=r.item,
        marked_by_self=r.marked_by == account_id,
    )
    if r.marked_by is None:
        marked_by = MarkedBy.UNKNOWN
    elif r.marked_by == account_id:
        marked_by = MarkedBy.SELF
    else:
        marked_by = MarkedBy.TEACHER
    return ExportEvent(event, marked_by, r.created_at)
