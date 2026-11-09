"""NT-03 on real Postgres (spec §3, §6, §8; ADR-0038): the guard matching the policy over
the role matrix, the rate limit (deleted ones don't count), the live audience, pins (one per
source), the feed and its window, moderation, mutes, the tick's `due` (members at send time,
mutes, the global switch, unreachable, delivered), the CHECKs, the cascades, prune, the
export, the app role, and 0024 up/down/up."""

import asyncio
import itertools
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.infrastructure.test_db_app_role import app_engine  # noqa: F401  # pyright: ignore[reportUnusedImport]
from tests.infrastructure.test_db_shalas import (
    _link,  # pyright: ignore[reportPrivateUsage]
    _person,  # pyright: ignore[reportPrivateUsage]
    _shala,  # pyright: ignore[reportPrivateUsage]
    _sql,  # pyright: ignore[reportPrivateUsage]
    _staff,  # pyright: ignore[reportPrivateUsage]
    _statements,  # pyright: ignore[reportPrivateUsage]
    _student,  # pyright: ignore[reportPrivateUsage]
)
from tristhana.application.policies import can_announce_to_shala
from tristhana.application.ports.announcements import NewAnnouncement
from tristhana.domain.announcements import PER_SOURCE_PER_DAY, Source, SourceKind
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.shalas import Membership, ShalaRole
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.announcements import SqlAnnouncementRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository

pytestmark = pytest.mark.db

R = ShalaRole
_n = itertools.count(1)


def _now() -> datetime:
    return datetime.now(UTC)


def _new(
    author: UUID,
    source: Source,
    text_: str = "Mysore closed Mon 10 Nov",
    pin: datetime | None = None,
) -> NewAnnouncement:
    return NewAnnouncement(
        author_id=author,
        source=source,
        text=f"{text_} #{next(_n)}",
        pinned_until=pin,
        since=_now() - timedelta(hours=24),
        limit=PER_SOURCE_PER_DAY,
    )


def _t(id: UUID) -> Source:
    return Source(SourceKind.TEACHER, id)


def _h(id: UUID) -> Source:
    return Source(SourceKind.SHALA, id)


async def _world(engine: AsyncEngine) -> dict[str, Any]:
    """A shala with every role, two students, and a teacher with two linked students."""
    w: dict[str, Any] = {}
    for name in ("owner", "manager", "teacher", "desk", "assistant", "s1", "s2", "x"):
        w[name], _ = await _person(engine, name.title())
    shala = await _shala(engine, w["owner"].id)
    w["shala"] = shala
    await _staff(engine, shala, w["owner"].id, w["manager"].id, R.ADMIN)
    await _staff(engine, shala, w["owner"].id, w["teacher"].id, R.TEACHER)
    await _staff(engine, shala, w["owner"].id, w["desk"].id, R.OFFICE)
    await _staff(engine, shala, w["owner"].id, w["assistant"].id, R.ASSISTANT)
    await _student(engine, shala, w["owner"].id, w["s1"].id)
    await _student(engine, shala, w["owner"].id, w["s2"].id)
    await _link(engine, w["s1"].id, w["teacher"].id)
    await _link(engine, w["s2"].id, w["teacher"].id)
    return w


# --- create ---------------------------------------------------------------------------


async def test_a_teacher_announces_to_their_students(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    with _statements(engine) as seen:
        posted = await repo.create(_new(w["teacher"].id, _t(w["teacher"].id)))
    assert len(seen) == 1
    assert posted.allowed
    assert posted.item is not None
    assert posted.item.audience == 2
    assert posted.item.shala_name is None


async def test_no_students_writes_nothing(engine: AsyncEngine) -> None:
    lone, _ = await _person(engine, "Lone")
    repo = SqlAnnouncementRepository(engine)
    posted = await repo.create(_new(lone.id, _t(lone.id)))
    assert posted.item is None
    assert not posted.limited
    assert (await _sql(engine, "SELECT count(*) FROM tristhana.announcement")).scalar_one() == 0


async def test_the_shala_audience_excludes_only_the_author(engine: AsyncEngine) -> None:
    w = await _world(engine)
    posted = await SqlAnnouncementRepository(engine).create(_new(w["desk"].id, _h(w["shala"])))
    assert posted.item is not None
    assert posted.item.audience == 6  # owner, manager, teacher, assistant, s1, s2
    assert posted.item.shala_name == "Ashtanga Almaty"
    assert posted.me is not None
    assert posted.me.roles == frozenset({R.OFFICE})


async def test_the_guard_matches_the_policy_for_every_member(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    expected = {
        "owner": True,
        "manager": True,
        "teacher": True,
        "desk": True,
        "assistant": False,
        "s1": False,
    }
    for who, allowed in expected.items():
        await _sql(engine, "DELETE FROM tristhana.announcement")
        posted = await repo.create(_new(w[who].id, _h(w["shala"])))
        assert posted.me is not None, who
        assert posted.allowed is allowed, who
        assert can_announce_to_shala(posted.me) is allowed, who
        assert (posted.item is not None) is allowed, who
    outsider = await repo.create(_new(w["x"].id, _h(w["shala"])))
    assert outsider.me is None
    assert not outsider.allowed
    unknown = await repo.create(_new(w["owner"].id, _h(uuid4())))
    assert unknown.me is None
    assert unknown.item is None


async def test_the_rate_limit_and_deleted_ones_dont_count(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    teacher = w["teacher"].id
    first = await repo.create(_new(teacher, _t(teacher)))
    for _ in range(PER_SOURCE_PER_DAY - 1):
        assert (await repo.create(_new(teacher, _t(teacher)))).item is not None
    limited = await repo.create(_new(teacher, _t(teacher)))
    assert limited.limited
    assert limited.item is None
    # another source of the same author is separate
    assert (await repo.create(_new(teacher, _h(w["shala"])))).item is not None
    assert first.item is not None
    managed = await repo.delete(teacher, first.item.id)
    assert managed.found
    assert managed.allowed
    assert (await repo.create(_new(teacher, _t(teacher)))).item is not None


async def test_a_new_pin_clears_only_the_same_sources_pin(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    teacher = w["teacher"].id
    week = _now() + timedelta(days=7)
    a = (await repo.create(_new(teacher, _t(teacher), pin=week))).item
    b = (await repo.create(_new(teacher, _h(w["shala"]), pin=week))).item
    c = (await repo.create(_new(teacher, _t(teacher), pin=week))).item
    unpinned = (await repo.create(_new(teacher, _t(teacher)))).item
    assert a and b and c and unpinned  # noqa: PT018
    rows = await _sql(engine, "SELECT id, pinned_until FROM tristhana.announcement")
    pins = {r.id: r.pinned_until for r in rows}
    assert pins[a.id] is None
    assert pins[b.id] is not None
    assert pins[c.id] is not None  # a send without a pin leaves the live one alone
    assert pins[unpinned.id] is None


# --- feed, sent, pin, delete, mute ------------------------------------------------------


async def test_the_feed_is_one_statement_with_pins_first(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    teacher, owner = w["teacher"].id, w["owner"].id
    old = await repo.create(_new(teacher, _t(teacher), "old", pin=_now() + timedelta(days=7)))
    await _sql(
        engine,
        "UPDATE tristhana.announcement SET created_at = now() - interval '40 days'",
    )
    gone = await repo.create(_new(owner, _h(w["shala"]), "shala"))
    newest = await repo.create(_new(teacher, _t(teacher), "newest"))
    await _sql(
        engine,
        "INSERT INTO tristhana.announcement (author_id, text, audience, created_at)"
        " VALUES (:a, 'too old', 1, now() - interval '35 days')",
        a=teacher,
    )
    now = _now()
    with _statements(engine) as seen:
        feed = await repo.feed(w["s1"].id, None, now - timedelta(days=30), now, 0, 10)
    assert len(seen) == 1
    assert feed is not None
    assert old.item and gone.item and newest.item  # noqa: PT018
    assert [i.id for i in feed.items] == [old.item.id, newest.item.id, gone.item.id]
    assert feed.items[0].pinned_until is not None
    assert feed.items[1].author_name == "Teacher"
    assert feed.items[2].source_name == "Ashtanga Almaty"
    assert not any(i.can_manage for i in feed.items)
    kinds = sorted((s.source.kind.value, s.name) for s in feed.sources)
    assert kinds == [("h", "Ashtanga Almaty"), ("t", "Teacher")]


async def test_a_foreign_source_is_none_and_one_hop_only(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    now = _now()
    since = now - timedelta(days=30)
    assert await repo.feed(w["x"].id, _t(w["teacher"].id), since, now, 0, 5) is None
    assert await repo.feed(w["x"].id, _h(w["shala"]), since, now, 0, 5) is None
    # reversed: the teacher reading a "student source"
    assert await repo.feed(w["teacher"].id, _t(w["s1"].id), since, now, 0, 5) is None
    one = await repo.feed(w["s1"].id, _t(w["teacher"].id), since, now, 0, 5)
    assert one is not None
    assert [s.source for s in one.sources] == [_t(w["teacher"].id)]


async def test_a_removed_author_loses_their_name(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    await repo.create(_new(w["desk"].id, _h(w["shala"])))
    await _sql(
        engine,
        "DELETE FROM tristhana.shala_staff WHERE account_id = :a",
        a=w["desk"].id,
    )
    now = _now()
    feed = await repo.feed(w["s1"].id, _h(w["shala"]), now - timedelta(days=30), now, 0, 5)
    assert feed is not None
    assert feed.items[0].author_name is None


async def test_paging_says_more(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    owner = w["owner"].id
    for _ in range(3):
        await repo.create(_new(owner, _h(w["shala"])))
    now = _now()
    since = now - timedelta(days=30)
    first = await repo.feed(w["s1"].id, None, since, now, 0, 2)
    second = await repo.feed(w["s1"].id, None, since, now, 2, 2)
    assert first is not None
    assert second is not None
    assert (len(first.items), first.more) == (2, True)
    assert (len(second.items), second.more) == (1, False)


async def test_sent_lists_my_own(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    mine = (await repo.create(_new(w["owner"].id, _h(w["shala"])))).item
    await repo.create(_new(w["desk"].id, _h(w["shala"])))
    sent = await repo.sent(w["owner"].id, _now() - timedelta(days=30))
    assert mine is not None
    assert [s.id for s in sent] == [mine.id]
    assert sent[0].audience == 6


async def test_moderation(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    item = (await repo.create(_new(w["desk"].id, _h(w["shala"])))).item
    assert item is not None
    assert await repo.delete(w["x"].id, item.id) == type(await repo.delete(w["x"].id, uuid4()))(
        False, False
    )
    teacher = await repo.delete(w["teacher"].id, item.id)
    assert (teacher.found, teacher.allowed) == (True, False)
    student = await repo.set_pin(w["s1"].id, item.id, _now() + timedelta(days=7))
    assert (student.found, student.allowed) == (True, False)
    pinned = await repo.set_pin(w["manager"].id, item.id, _now() + timedelta(days=7))
    assert pinned.allowed
    assert pinned.item is not None
    assert pinned.item.pinned_until is not None
    unpinned = await repo.set_pin(w["desk"].id, item.id, None)
    assert unpinned.item is not None
    assert unpinned.item.pinned_until is None
    gone = await repo.delete(w["owner"].id, item.id)
    assert (gone.found, gone.allowed) == (True, True)
    again = await repo.delete(w["owner"].id, item.id)
    assert again.found is False


async def test_a_teacher_items_are_managed_by_the_author_only(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    item = (await repo.create(_new(w["teacher"].id, _t(w["teacher"].id)))).item
    assert item is not None
    s1 = await repo.set_pin(w["s1"].id, item.id, None)
    assert (s1.found, s1.allowed) == (True, False)
    owner = await repo.set_pin(w["owner"].id, item.id, None)
    assert owner.found is False  # not a linked student: as if it didn't exist


async def test_mute_is_keyed_on_the_caller(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    assert await repo.set_mute(w["s1"].id, _t(w["teacher"].id), True)
    assert await repo.set_mute(w["s1"].id, _h(w["shala"]), True)
    assert await repo.set_mute(w["manager"].id, _h(w["shala"]), True)
    assert not await repo.set_mute(w["x"].id, _t(w["teacher"].id), True)
    assert not await repo.set_mute(w["x"].id, _h(w["shala"]), True)
    now = _now()
    feed = await repo.feed(w["s1"].id, None, now - timedelta(days=30), now, 0, 5)
    assert feed is not None
    assert all(s.muted for s in feed.sources)


# --- due ---------------------------------------------------------------------------------


async def test_due_is_one_statement_over_the_live_audience(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    owner = w["owner"].id
    await repo.set_mute(w["manager"].id, _h(w["shala"]), True)
    await SqlNotificationRepository(engine).patch(
        w["assistant"].id, {"announcements_on": False}, DEFAULTS
    )
    await SqlNotificationRepository(engine).mark_unreachable(w["teacher"].id, _now())
    item = (await repo.create(_new(owner, _h(w["shala"])))).item
    assert item is not None
    late, _ = await _person(engine, "Late")
    await _student(engine, w["shala"], owner, late.id)
    now = _now()
    with _statements(engine) as seen:
        due = await repo.due(now - timedelta(hours=24), now, 100)
    assert len(seen) == 1
    got = {d.account_id for d in due}
    assert got == {w["desk"].id, w["s1"].id, w["s2"].id}
    one = next(d for d in due if d.account_id == w["s1"].id)
    assert (one.source_name, one.author_name, one.zone) == (
        "Ashtanga Almaty",
        "Owner",
        "Asia/Almaty",
    )
    assert one.quiet == DEFAULTS.quiet
    # delivered, and a removed member: gone from the next tick
    notes = SqlNotificationRepository(engine)
    assert await notes.claim(w["s1"].id, f"ann:{item.id}", "announcement", now.date())
    await notes.finish(w["s1"].id, f"ann:{item.id}", "sent")
    await _sql(engine, "DELETE FROM tristhana.shala_student WHERE account_id = :a", a=w["s2"].id)
    after = await repo.due(now - timedelta(hours=24), now, 100)
    assert {d.account_id for d in after} == {w["desk"].id}


async def test_a_failed_push_is_retried_until_its_limit(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    item = (await repo.create(_new(w["teacher"].id, _t(w["teacher"].id)))).item
    assert item is not None
    notes = SqlNotificationRepository(engine)
    key = f"ann:{item.id}"
    now = _now()
    assert await notes.claim(w["s1"].id, key, "announcement", now.date())
    await notes.finish(w["s1"].id, key, "failed")
    due = await repo.due(now - timedelta(hours=24), now, 100)
    assert w["s1"].id in {d.account_id for d in due}
    await _sql(
        engine,
        "UPDATE tristhana.notification_delivery SET attempts = 3 WHERE dedupe_key = :k",
        k=key,
    )
    due = await repo.due(now - timedelta(hours=24), now, 100)
    assert w["s1"].id not in {d.account_id for d in due}


async def test_old_ones_are_not_due_and_prune_at_90_days(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    await repo.create(_new(w["teacher"].id, _t(w["teacher"].id)))
    await _sql(engine, "UPDATE tristhana.announcement SET created_at = now() - interval '91 days'")
    now = _now()
    assert await repo.due(now - timedelta(hours=24), now, 100) == []
    assert await repo.prune(now - timedelta(days=90)) == 1


# --- schema ------------------------------------------------------------------------------


@pytest.mark.parametrize(("text_", "audience"), [("", 1), ("x" * 1001, 1), ("ok", -1)])
async def test_the_checks(engine: AsyncEngine, text_: str, audience: int) -> None:
    me, _ = await _person(engine)
    with pytest.raises(IntegrityError):
        await _sql(
            engine,
            "INSERT INTO tristhana.announcement (author_id, text, audience) VALUES (:a, :t, :n)",
            a=me.id,
            t=text_,
            n=audience,
        )


async def test_the_ledger_accepts_announcements(engine: AsyncEngine) -> None:
    me, _ = await _person(engine)
    notes = SqlNotificationRepository(engine)
    assert await notes.claim(me.id, "ann:x", "announcement", _now().date())


async def test_cascades(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    await repo.create(_new(w["teacher"].id, _t(w["teacher"].id)))
    await repo.create(_new(w["desk"].id, _h(w["shala"])))
    await repo.create(_new(w["owner"].id, _h(w["shala"])))
    count = "SELECT count(*) FROM tristhana.announcement"
    await _sql(engine, "DELETE FROM tristhana.account WHERE id = :a", a=w["teacher"].id)
    assert (await _sql(engine, count)).scalar_one() == 2
    await _sql(engine, "DELETE FROM tristhana.shala WHERE id = :s", s=w["shala"])
    assert (await _sql(engine, count)).scalar_one() == 0


async def test_the_mute_columns_default_false(engine: AsyncEngine) -> None:
    w = await _world(engine)
    for table in ("teacher_link", "shala_staff", "shala_student"):
        rows = await _sql(engine, f"SELECT bool_or(announcements_muted) FROM tristhana.{table}")  # noqa: S608
        assert rows.scalar_one() is False, table
    assert w


async def test_announcing_works_as_the_app_role(app_engine: AsyncEngine) -> None:  # noqa: F811
    w = await _world(app_engine)
    repo = SqlAnnouncementRepository(app_engine)
    item = (
        await repo.create(_new(w["owner"].id, _h(w["shala"]), pin=_now() + timedelta(days=7)))
    ).item
    assert item is not None
    now = _now()
    assert await repo.feed(w["s1"].id, None, now - timedelta(days=30), now, 0, 5)
    assert await repo.set_mute(w["s1"].id, _h(w["shala"]), True)
    assert (await repo.set_pin(w["owner"].id, item.id, None)).allowed
    assert await repo.due(now - timedelta(hours=24), now, 10)
    assert (await repo.delete(w["owner"].id, item.id)).allowed
    assert await repo.prune(now - timedelta(days=90)) == 0


async def test_0024_up_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    exists = text(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name = 'announcement'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0023")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(exists)).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(exists)).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)


def test_membership_shape() -> None:
    assert Membership(uuid4(), False, frozenset({R.OFFICE}), False).staff


async def test_the_export_holds_my_sent_only(engine: AsyncEngine) -> None:
    from datetime import date

    from tests.infrastructure.test_db_shalas import KEYS
    from tristhana.infrastructure.crypto import FieldCipher
    from tristhana.infrastructure.db.export import SqlExportRepository

    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    await repo.set_mute(w["s1"].id, _t(w["teacher"].id), True)
    await repo.create(_new(w["teacher"].id, _t(w["teacher"].id), "Led class"))
    await repo.create(_new(w["teacher"].id, _h(w["shala"]), "Closed"))
    export = SqlExportRepository(engine, FieldCipher(KEYS))
    mine = await export.snapshot(w["teacher"].id, DEFAULTS, date(2026, 1, 1))
    theirs = await export.snapshot(w["s1"].id, DEFAULTS, date(2026, 1, 1))
    assert mine is not None
    assert theirs is not None
    assert sorted((a.to, a.shala) for a in mine.announcements) == [
        ("shala", "Ashtanga Almaty"),
        ("students", None),
    ]
    assert theirs.announcements == ()  # received text is someone else's
    assert [k.announcements_muted for k in theirs.links] == [True]
    assert [k.announcements_muted for k in mine.links] == [None, None]  # never the students'


async def test_a_demoted_author_cannot_pin_but_can_delete(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlAnnouncementRepository(engine)
    item = (await repo.create(_new(w["teacher"].id, _h(w["shala"])))).item
    assert item is not None
    await _sql(
        engine,
        "UPDATE tristhana.shala_staff SET roles = '{assistant}' WHERE account_id = :a",
        a=w["teacher"].id,
    )
    denied = await repo.set_pin(w["teacher"].id, item.id, _now() + timedelta(days=7))
    assert (denied.found, denied.allowed) == (True, False)
    assert denied.me is not None
    assert denied.me.roles == frozenset({R.ASSISTANT})
    assert denied.author_id == w["teacher"].id
    gone = await repo.delete(w["teacher"].id, item.id)
    assert (gone.found, gone.allowed) == (True, True)


async def test_two_ticks_claim_a_push_once(engine: AsyncEngine) -> None:
    w = await _world(engine)
    item = (
        await SqlAnnouncementRepository(engine).create(_new(w["owner"].id, _h(w["shala"])))
    ).item
    assert item is not None
    notes = SqlNotificationRepository(engine)
    key = f"ann:{item.id}"
    claims = await asyncio.gather(
        *(notes.claim(w["s1"].id, key, "announcement", _now().date()) for _ in range(5))
    )
    assert sorted(claims) == [False, False, False, False, True]
