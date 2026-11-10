"""ID-05 on real Postgres (spec §5, §9, §10; ADR-0042): migration 0027's `directory_listing`.
`save` plans against the locked row and writes nothing when the plan raises; `withdraw` keeps
only the timestamps; `decide` matches the revision and clears the note, and of two concurrent
decides one wins; the CHECKs; the cascade and `checked_by` SET NULL; the mark rides on the
teacher-link `preview` and `overview` with no extra statement and only for a listed row; the
export has the section and never `checked_by`; up/down/up with no drift; the app role."""

import asyncio
import base64
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.infrastructure.test_db_app_role import app_engine  # noqa: F401  # pyright: ignore[reportUnusedImport]
from tests.infrastructure.test_db_shalas import (  # pyright: ignore[reportPrivateUsage]
    _person,  # pyright: ignore[reportPrivateUsage]
)
from tristhana.application.ports.notifications import Recipient
from tristhana.domain.directory_listing import (
    DeclaredLevel,
    Details,
    Listing,
    ListingMark,
    ListingStatus,
    ListingWait,
    Outcome,
    Step,
    next_state,
)
from tristhana.domain.notifications import DEFAULTS
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.directory_listing import SqlListingRepository
from tristhana.infrastructure.db.export import SqlExportRepository
from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
NOW = datetime(2026, 11, 11, 4, 30, tzinfo=UTC)
TODAY = date(2026, 11, 11)
ANNA = Details("Anna Petrova", "Russia", DeclaredLevel.AUTHORISED_2, "anna.example")
CODE = "aB3dE6gH9jK2mN5p"


async def _sql(engine: AsyncEngine, statement: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        result = await conn.execute(text(statement), params)
        await conn.commit()
        return result


@contextmanager
def _statements(engine: AsyncEngine) -> Generator[list[str]]:
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        if "tristhana." in statement:
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


async def _send(
    repo: SqlListingRepository, me: UUID, details: Details = ANNA, at: datetime = NOW
) -> Listing:
    saved = await repo.save(me, details, lambda current: next_state(current, details, at), at)
    return saved.listing


async def _listed(repo: SqlListingRepository, me: UUID, admin: UUID) -> Listing:
    sent = await _send(repo, me)
    assert await repo.decide(me, sent.revision, Outcome.LISTED, TODAY, admin) is not None
    found = await repo.get(me)
    assert found is not None
    return found


async def test_a_first_send_then_an_edit_in_place(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Anna")
    repo = SqlListingRepository(engine)
    assert await repo.get(me.id) is None
    sent = await _send(repo, me.id)
    assert sent == Listing(
        ListingStatus.PENDING, "Anna Petrova", "Russia", DeclaredLevel.AUTHORISED_2,
        "anna.example", 1, NOW, None,
    )  # fmt: skip
    later = NOW + timedelta(minutes=5)
    edited = Details("Anna Petrova-Smith", "Russia", None, None)
    saved = await repo.save(me.id, edited, lambda c: next_state(c, edited, later), later)
    assert saved.step is Step.EDIT
    assert saved.listing == Listing(
        ListingStatus.PENDING, "Anna Petrova-Smith", "Russia", None, None, 2, NOW, None
    )
    assert await repo.get(me.id) == saved.listing


async def test_a_refused_plan_writes_nothing(engine: AsyncEngine) -> None:
    me, _ = await _person(engine)
    admin, _ = await _person(engine, "Admin")
    repo = SqlListingRepository(engine)
    sent = await _send(repo, me.id)
    await repo.decide(me.id, sent.revision, Outcome.NOT_FOUND, TODAY, admin.id)
    before = await repo.get(me.id)
    soon = NOW + timedelta(hours=1)
    with pytest.raises(ListingWait):
        await repo.save(me.id, ANNA, lambda c: next_state(c, ANNA, soon), soon)
    assert await repo.get(me.id) == before
    next_day = NOW + timedelta(hours=24)
    again = await repo.save(me.id, ANNA, lambda c: next_state(c, ANNA, next_day), next_day)
    assert (again.step, again.listing.status, again.listing.requested_at) == (
        Step.SEND,
        ListingStatus.PENDING,
        next_day,
    )


async def test_two_first_sends_at_once_leave_one_row(engine: AsyncEngine) -> None:
    me, _ = await _person(engine)
    repo = SqlListingRepository(engine)
    steps = await asyncio.gather(
        repo.save(me.id, ANNA, lambda c: next_state(c, ANNA, NOW), NOW),
        repo.save(me.id, ANNA, lambda c: next_state(c, ANNA, NOW), NOW),
    )
    assert sorted(s.step.value for s in steps) == ["edit", "send"]  # the second sees the first
    found = await repo.get(me.id)
    assert found is not None
    assert found.revision == 2


async def test_listed_then_level_only_then_a_name_change(engine: AsyncEngine) -> None:
    me, _ = await _person(engine)
    admin, _ = await _person(engine, "Admin")
    repo = SqlListingRepository(engine)
    listed = await _listed(repo, me.id, admin.id)
    assert (listed.status, listed.checked_on, listed.note) == (ListingStatus.LISTED, TODAY, None)

    level = Details("Anna Petrova", "Russia", DeclaredLevel.CERTIFIED, "ignored")
    saved = await repo.save(me.id, level, lambda c: next_state(c, level, NOW), NOW)
    assert saved.step is Step.LEVEL_ONLY
    assert (saved.listing.status, saved.listing.level, saved.listing.checked_on) == (
        ListingStatus.LISTED,
        DeclaredLevel.CERTIFIED,
        TODAY,
    )
    assert saved.listing.note is None  # a note lives only while pending

    later = NOW + timedelta(days=2)
    renamed = Details("Anna Smith", "Russia", DeclaredLevel.CERTIFIED, None)
    again = await repo.save(me.id, renamed, lambda c: next_state(c, renamed, later), later)
    assert again.step is Step.RECHECK
    assert (again.listing.status, again.listing.checked_on, again.listing.requested_at) == (
        ListingStatus.PENDING,
        None,
        later,
    )
    row = (
        await _sql(engine, "SELECT checked_by, decided_at FROM tristhana.directory_listing")
    ).one()
    assert tuple(row) == (None, None)


async def test_withdraw_keeps_only_the_timestamps_and_is_idempotent(engine: AsyncEngine) -> None:
    me, _ = await _person(engine)
    other, _ = await _person(engine, "Other")
    repo = SqlListingRepository(engine)
    await repo.withdraw(other.id)  # no row: stays no row
    assert await repo.get(other.id) is None
    await _send(repo, me.id)
    await repo.withdraw(me.id)
    found = await repo.get(me.id)
    assert found == Listing(ListingStatus.WITHDRAWN, None, None, None, None, 2, NOW, None)
    await repo.withdraw(me.id)
    again = await repo.get(me.id)
    assert again is not None
    assert again.revision == 2
    assert await repo.request(me.id) is None  # nothing for the checker to see


async def test_decide_matches_the_revision_and_tells_who_to_tell(engine: AsyncEngine) -> None:
    me, key = await _person(engine, "Anna")
    admin, _ = await _person(engine, "Admin")
    repo = SqlListingRepository(engine)
    sent = await _send(repo, me.id)
    assert await repo.decide(me.id, sent.revision + 1, Outcome.LISTED, TODAY, admin.id) is None
    assert await repo.decide(uuid4(), 1, Outcome.LISTED, TODAY, admin.id) is None
    decided = await repo.decide(me.id, sent.revision, Outcome.LISTED, TODAY, admin.id)
    assert decided is not None
    assert (decided.teacher, decided.name_as_listed, decided.was_listed) == (
        Recipient(key.provider_user_id, "en"),
        "Anna Petrova",
        False,
    )
    assert await repo.decide(me.id, sent.revision, Outcome.NOT_FOUND, TODAY, admin.id) is None
    found = await repo.get(me.id)
    assert found is not None
    ended = await repo.decide(me.id, found.revision, Outcome.NOT_FOUND, TODAY, admin.id)
    assert ended is not None
    assert ended.was_listed
    gone = await repo.get(me.id)
    assert gone is not None
    assert (gone.status, gone.checked_on) == (ListingStatus.NOT_FOUND, None)
    assert await repo.decide(me.id, gone.revision, Outcome.LISTED, TODAY, admin.id) is None


async def test_two_decides_at_once_one_wins(engine: AsyncEngine) -> None:
    me, _ = await _person(engine)
    admin, _ = await _person(engine, "Admin")
    repo = SqlListingRepository(engine)
    sent = await _send(repo, me.id)
    results = await asyncio.gather(
        repo.decide(me.id, sent.revision, Outcome.LISTED, TODAY, admin.id),
        repo.decide(me.id, sent.revision, Outcome.NOT_FOUND, TODAY, admin.id),
    )
    assert [r is None for r in results].count(True) == 1


async def test_an_edit_between_the_card_and_the_tap_wins(engine: AsyncEngine) -> None:
    me, _ = await _person(engine)
    admin, _ = await _person(engine, "Admin")
    repo = SqlListingRepository(engine)
    sent = await _send(repo, me.id)
    other = Details("Somebody Else", "Russia", None, None)
    await repo.save(me.id, other, lambda c: next_state(c, other, NOW), NOW)
    assert await repo.decide(me.id, sent.revision, Outcome.LISTED, TODAY, admin.id) is None
    found = await repo.get(me.id)
    assert found is not None
    assert found.status is ListingStatus.PENDING


async def test_the_review_lists_and_counts_in_one_statement(engine: AsyncEngine) -> None:
    admin, _ = await _person(engine, "Admin")
    repo = SqlListingRepository(engine)
    empty = await repo.requests(False, 0)
    assert (empty.rows, empty.waiting, empty.listed, empty.oldest_check) == ((), 0, 0, None)
    people = [(await _person(engine, f"T{n}"))[0].id for n in range(12)]
    for n, id_ in enumerate(people):
        await _send(repo, id_, at=NOW + timedelta(minutes=n))
    first_listed = await repo.get(people[0])
    assert first_listed is not None
    await repo.decide(people[0], first_listed.revision, Outcome.LISTED, date(2026, 5, 2), admin.id)
    with _statements(engine) as seen:
        waiting = await repo.requests(False, 0)
    assert len(seen) == 1
    assert (waiting.waiting, waiting.listed, waiting.oldest_check) == (11, 1, date(2026, 5, 2))
    assert [r.account_id for r in waiting.rows] == people[1:11]  # oldest first
    assert waiting.rows[0].at == TODAY
    second = await repo.requests(False, 1)
    assert [r.account_id for r in second.rows] == people[11:]
    listed = await repo.requests(True, 0)
    assert [(r.account_id, r.at) for r in listed.rows] == [(people[0], date(2026, 5, 2))]
    past = await repo.requests(True, 5)
    assert (past.rows, past.listed) == ((), 1)  # counts come back with an empty page

    card = await repo.request(people[1])
    assert card is not None
    assert (card.display_name, card.listing.note) == ("T1", "anna.example")


async def test_recipients_are_the_admins_telegram_identities(engine: AsyncEngine) -> None:
    admin, key = await _person(engine, "Admin")
    repo = SqlListingRepository(engine)
    assert await repo.recipients(frozenset()) == ()
    found = await repo.recipients(frozenset({admin.id, uuid4()}))
    assert found == (Recipient(key.provider_user_id, "en"),)


@pytest.mark.parametrize(
    "values",
    [
        "status = 'approved'",
        "declared_level = 'level-3'",
        "name_as_listed = ''",
        "name_as_listed = repeat('a', 101)",
        "region = repeat('r', 61)",
        "note = repeat('n', 301)",
        "name_as_listed = NULL",
        "status = 'withdrawn'",
        "status = 'listed'",  # no check date
        "status = 'not_found'",  # a note outside pending
    ],
)
async def test_the_checks(engine: AsyncEngine, values: str) -> None:
    me, _ = await _person(engine)
    await _send(SqlListingRepository(engine), me.id)
    with pytest.raises(IntegrityError):
        await _sql(engine, f"UPDATE tristhana.directory_listing SET {values}")  # noqa: S608


async def test_the_row_goes_with_its_account_and_a_deleted_checker_leaves_the_line(
    engine: AsyncEngine,
) -> None:
    me, _ = await _person(engine, "Anna")
    admin, _ = await _person(engine, "Admin")
    repo = SqlListingRepository(engine)
    await _listed(repo, me.id, admin.id)
    await _sql(engine, "DELETE FROM tristhana.account WHERE id = :id", id=admin.id)
    row = (await _sql(engine, "SELECT status, checked_by FROM tristhana.directory_listing")).one()
    assert tuple(row) == ("listed", None)
    await _sql(engine, "DELETE FROM tristhana.account WHERE id = :id", id=me.id)
    count = await _sql(engine, "SELECT count(*) FROM tristhana.directory_listing")
    assert count.scalar_one() == 0


async def test_the_mark_rides_on_preview_and_overview_with_no_extra_statement(
    engine: AsyncEngine,
) -> None:
    anna, _ = await _person(engine, "Anna")
    boris, _ = await _person(engine, "Boris")
    admin, _ = await _person(engine, "Admin")
    student, _ = await _person(engine, "Clara")
    links = SqlTeacherLinkRepository(engine)
    listings = SqlListingRepository(engine)
    await links.invite(anna.id, CODE)
    for teacher in (anna, boris):
        await _sql(
            engine,
            "INSERT INTO tristhana.teacher_link (student_id, teacher_id, linked_on)"
            " VALUES (:s, :t, :d)",
            s=student.id, t=teacher.id, d=TODAY,
        )  # fmt: skip
    await _sql(
        engine,
        "INSERT INTO tristhana.teacher_link (student_id, teacher_id, linked_on)"
        " VALUES (:s, :t, :d)",
        s=anna.id, t=student.id, d=TODAY,
    )  # fmt: skip

    with _statements(engine) as seen:
        before = await links.preview(CODE, student.id)
        plain = await links.overview(student.id)
    assert len(seen) == 2  # one each, with or without a listing row
    assert before is not None
    assert before.listing is None
    assert plain.listings == {}

    # Waiting, then not found, then withdrawn: never a mark.
    sent = await _send(listings, anna.id)
    assert (await links.preview(CODE, student.id)).listing is None  # type: ignore[union-attr]
    await listings.decide(anna.id, sent.revision, Outcome.NOT_FOUND, TODAY, admin.id)
    assert (await links.preview(CODE, student.id)).listing is None  # type: ignore[union-attr]
    await listings.withdraw(anna.id)
    assert (await links.overview(student.id)).listings == {}

    # Clara is listed too: a student row must still never carry a mark.
    await _listed(listings, student.id, admin.id)
    later = NOW + timedelta(days=2)
    saved = await listings.save(anna.id, ANNA, lambda c: next_state(c, ANNA, later), later)
    await listings.decide(anna.id, saved.listing.revision, Outcome.LISTED, TODAY, admin.id)

    mark = ListingMark("Anna Petrova", TODAY, DeclaredLevel.AUTHORISED_2)
    with _statements(engine) as seen:
        after = await links.preview(CODE, student.id)
        found = await links.overview(student.id)
    assert len(seen) == 2
    assert after is not None
    assert after.listing == mark
    assert found.listings == {anna.id: mark}  # Boris has no entry at all
    mine = await links.overview(anna.id)
    # Anna's teacher is Clara (listed); Clara as Anna's student would never carry a mark.
    assert mine.listings == {
        student.id: ListingMark("Anna Petrova", TODAY, DeclaredLevel.AUTHORISED_2)
    }


async def test_the_export_has_my_request_and_never_who_checked_it(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Anna")
    admin, _ = await _person(engine, "Admin")
    export = SqlExportRepository(engine, FieldCipher(KEYS))
    empty = await export.snapshot(me.id, DEFAULTS, TODAY)
    assert empty is not None
    assert empty.listing is None
    listed = await _listed(SqlListingRepository(engine), me.id, admin.id)
    owned = await export.snapshot(me.id, DEFAULTS, TODAY)
    assert owned is not None
    assert owned.listing == listed
    assert not hasattr(owned.listing, "checked_by")
    theirs = await export.snapshot(admin.id, DEFAULTS, TODAY)
    assert theirs is not None
    assert theirs.listing is None  # a row an admin checked is not the admin's data


async def test_0027_up_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    exists = text(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name = 'directory_listing'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0026")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(exists)).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(exists)).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)


async def test_the_listing_works_as_the_app_role(app_engine: AsyncEngine) -> None:  # noqa: F811
    me, _ = await _person(app_engine, "Anna")
    admin, _ = await _person(app_engine, "Admin")
    repo = SqlListingRepository(app_engine)
    sent = await _send(repo, me.id)
    edited = Details("Anna P.", "Russia", None, None)
    await repo.save(me.id, edited, lambda c: next_state(c, edited, NOW), NOW)
    assert (await repo.requests(False, 0)).waiting == 1
    assert await repo.request(me.id) is not None
    assert await repo.recipients(frozenset({admin.id}))
    assert await repo.decide(me.id, sent.revision + 1, Outcome.LISTED, TODAY, admin.id)
    await repo.withdraw(me.id)
    export = SqlExportRepository(app_engine, FieldCipher(KEYS))
    owned = await export.snapshot(me.id, DEFAULTS, TODAY)
    assert owned is not None
    assert owned.listing is not None
    assert owned.listing.status is ListingStatus.WITHDRAWN
