"""ST-04 timeline and the Q159 fix on fakes (spec §4, §8): `GetTimeline` reads the caller's own
record in one repository call, says `set` false when unset and passes `truncated` through; the
in-memory view after a write (`_after`) sets `position_event` on a start, a give or a change and
keeps it on item events, however old it is. A frozen clock throughout."""

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from tests.application.test_progression import (
    BHUJA,
    KURMASANA,
    NAVASANA,
    PASASANA,
    Env,
    _me,  # pyright: ignore[reportPrivateUsage]
    track,
)
from tristhana.application.ports.progression import TimelineRead
from tristhana.application.progression import GetTimeline
from tristhana.domain.progression import (
    HISTORY_LIMIT,
    Celebration,
    CelebrationKind,
    Earlier,
    EventKind,
    ProgressionEvent,
)

K = CelebrationKind
STARTED_ON = date(2026, 10, 1)


@dataclass
class RecordingTimeline:
    """Hands back `found` and records which account was read."""

    found: TimelineRead = field(default_factory=lambda: TimelineRead(()))
    read: list[UUID] = field(default_factory=list[UUID])

    async def timeline(self, account_id: UUID) -> TimelineRead:
        self.read.append(account_id)
        return self.found


# GetTimeline


async def test_the_timeline_is_one_call_for_the_callers_own_account() -> None:
    env, me, other = Env(), _me(), _me()
    await env.set.execute(other, KURMASANA)
    await env.set.execute(me, NAVASANA)
    await env.give.execute(me, BHUJA)
    env.repo.calls.clear()

    found = await GetTimeline(env.repo, track()).execute(me)

    assert env.repo.calls == ["timeline"]
    assert found.set is True
    assert found.truncated is False
    assert [e.event.kind for e in found.entries] == [EventKind.GIVEN, EventKind.START]
    assert found.entries[0].celebrations == (Celebration(K.NEW_ASANA, "primary", BHUJA.key),)
    assert all(e.event.after != KURMASANA for e in found.entries)  # not the other account's


async def test_the_use_case_passes_only_the_principals_id() -> None:
    repo, me = RecordingTimeline(), _me()

    await GetTimeline(repo, track()).execute(me)  # type: ignore[arg-type]

    assert repo.read == [me.account.id]


async def test_unset_is_not_set_and_empty() -> None:
    env, me = Env(), _me()

    found = await GetTimeline(env.repo, track()).execute(me)

    assert (found.set, found.truncated, found.entries) == (False, False, ())


async def test_truncated_passes_through() -> None:
    start = ProgressionEvent(7, EventKind.START, STARTED_ON, after=NAVASANA)
    repo = RecordingTimeline(TimelineRead((start,), True))

    found = await GetTimeline(repo, track()).execute(_me())  # type: ignore[arg-type]

    assert found.truncated is True
    assert found.set is True
    assert [e.event for e in found.entries] == [start]


async def test_a_cut_history_replays_from_what_older_events_reached() -> None:
    """Kurmasana was given before the kept window: giving it again inside it is quiet."""
    changed = ProgressionEvent(8, EventKind.CHANGED, STARTED_ON, before=KURMASANA, after=NAVASANA)
    given = ProgressionEvent(9, EventKind.GIVEN, STARTED_ON, before=NAVASANA, after=KURMASANA)
    before = Earlier(frozenset({NAVASANA, KURMASANA}), frozenset({"drop-backs"}))
    repo = RecordingTimeline(TimelineRead((changed, given), True, before))

    found = await GetTimeline(repo, track()).execute(_me())  # type: ignore[arg-type]

    assert [e.celebrations for e in found.entries] == [(), ()]


# `_after`: position_event in the in-memory view


async def test_a_start_a_give_and_a_change_set_the_position_event() -> None:
    env, me = Env(), _me()

    started = await env.set.execute(me, NAVASANA)
    assert started.view.position_event == started.event
    given = await env.give.execute(me, BHUJA)
    assert given.view.position_event == given.event
    changed = await env.set.execute(me, PASASANA)
    assert changed.event is not None
    assert changed.event.kind is EventKind.CHANGED
    assert changed.view.position_event == changed.event


async def test_item_events_keep_the_position_event() -> None:
    env, me = Env(), _me()
    await env.set.execute(me, NAVASANA)
    given = await env.give.execute(me, BHUJA)

    ticked = await env.item.execute(me, "drop-backs", True)
    removed = await env.item.execute(me, "drop-backs", False)

    assert ticked.view.position_event == given.event
    assert removed.view.position_event == given.event


async def test_the_position_event_is_kept_past_the_history_limit() -> None:
    """Q159: the give stays the view's position event after more item events than History
    holds, and the in-memory view matches a fresh read."""
    env, me = Env(), _me()
    await env.set.execute(me, NAVASANA)
    given = await env.give.execute(me, BHUJA)
    last = None
    for n in range(HISTORY_LIMIT + 5):
        last = await env.item.execute(me, "drop-backs", n % 2 == 0)

    assert last is not None
    assert given.event is not None
    assert given.event not in last.view.events
    assert last.view.position_event == given.event
    assert (await env.repo.get(me.account.id)).position_event == given.event


async def test_a_no_op_keeps_the_view() -> None:
    env, me = Env(), _me()
    started = await env.set.execute(me, NAVASANA)

    again = await env.set.execute(me, NAVASANA)

    assert again.event is None
    assert again.view.position_event == started.event
