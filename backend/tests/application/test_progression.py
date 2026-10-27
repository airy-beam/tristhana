"""Progression use cases on fakes (PR-08, ADR-0026): set → START then CHANGED (no-op when
equal, never celebrates), new asana (forward only, needs a position, celebrates from the
history), items, compare-and-set (a stale view or a lost race raises, no celebration),
latest-only undo (a real give after it celebrates again), the "Not new" answer, dates in
the caller's zone, the practice save hint and the "🧘 My practice" presets."""

from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path
from uuid import uuid4

import pytest

from tests.fakes import FixedClock, InMemoryDays, InMemoryPractices, InMemoryProgression
from tristhana.application import policies
from tristhana.application.policies import Principal
from tristhana.application.practice import GetPracticePresets, SavePractice
from tristhana.application.practice_patch import PracticePatch
from tristhana.application.progression import (
    DismissNewAsanaHint,
    GetProgression,
    MarkItem,
    MarkNewAsana,
    NotLatest,
    ProgressionChanged,
    SetPractice,
    UndoProgression,
)
from tristhana.domain.accounts import Account
from tristhana.domain.days import DateInFuture, DateTooEarly, DayLog, DayStatus
from tristhana.domain.practice import (
    Practice,
    PracticeCatalog,
    PracticeContext,
    PracticeLength,
)
from tristhana.domain.progression import (
    Celebration,
    CelebrationKind,
    EventKind,
    NotForward,
    Position,
    ProgressionNotSet,
    Track,
)
from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog

NOW = datetime(2026, 10, 27, 6, 0, tzinfo=UTC)  # Almaty: Tue Oct 27, 11:00
TUE, MON = date(2026, 10, 27), date(2026, 10, 26)
NAVASANA = Position("primary", "navasana")
BHUJA = Position("primary", "bhujapidasana")
KURMASANA = Position("primary", "kurmasana")
SETU = Position("primary", "setu-bandhasana")
PASASANA = Position("intermediate", "pasasana")


@cache
def catalog() -> PracticeCatalog:
    return load_practice_catalog(Path(__file__).resolve().parents[3] / "data" / "seed").catalog


@cache
def track() -> Track:
    return Track(catalog())


def _me(timezone: str | None = "Asia/Almaty") -> Principal:
    return Principal(
        Account(
            id=uuid4(),
            display_name="A",
            locale="en",
            timezone=timezone,
            last_seen_at=NOW,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )


class Env:
    def __init__(self, now: datetime = NOW) -> None:
        self.days = InMemoryDays()
        self.repo = InMemoryProgression(self.days)
        self.practices = InMemoryPractices(self.days)
        clock = FixedClock(now)
        self.get = GetProgression(self.repo, self.practices, track(), clock)
        self.set = SetPractice(self.repo, track(), clock)
        self.give = MarkNewAsana(self.repo, track(), clock)
        self.item = MarkItem(self.repo, track(), clock)
        self.undo = UndoProgression(self.repo)
        self.dismiss = DismissNewAsanaHint(self.repo)


async def test_set_starts_then_changes_without_celebrating() -> None:
    env, me = Env(), _me()
    first = await env.set.execute(me, NAVASANA)
    assert first.event is not None
    assert first.event.kind is EventKind.START
    assert first.event.occurred_on == TUE
    assert first.celebrations == ()
    again = await env.set.execute(me, NAVASANA)
    assert again.event is None
    changed = await env.set.execute(me, PASASANA)
    assert changed.event is not None
    assert changed.event.kind is EventKind.CHANGED
    assert changed.celebrations == ()
    assert changed.view.progression is not None
    assert changed.view.progression.position == PASASANA
    assert [e.kind for e in changed.view.events] == [EventKind.CHANGED, EventKind.START]


async def test_one_read_and_one_write_per_change() -> None:
    env, me = Env(), _me()
    await env.set.execute(me, NAVASANA)
    env.repo.calls.clear()
    await env.give.execute(me, BHUJA)
    assert env.repo.calls == ["get", "apply"]


async def test_new_asana_celebrates_and_the_view_is_built_in_memory() -> None:
    env, me = Env(), _me()
    await env.set.execute(me, NAVASANA)
    result = await env.give.execute(me, BHUJA)
    assert result.celebrations == (
        Celebration(CelebrationKind.NEW_ASANA, "primary", "bhujapidasana"),
    )
    assert result.view == (await env.repo.get(me.account.id))


async def test_new_asana_needs_a_position_and_must_go_forward() -> None:
    env, me = Env(), _me()
    with pytest.raises(ProgressionNotSet):
        await env.give.execute(me, NAVASANA)
    await env.set.execute(me, KURMASANA)
    with pytest.raises(NotForward):
        await env.give.execute(me, NAVASANA)
    with pytest.raises(NotForward):
        await env.give.execute(me, KURMASANA)  # a double tap


async def test_a_stale_view_raises_and_writes_nothing() -> None:
    env, me = Env(), _me()
    start = await env.set.execute(me, NAVASANA)
    assert start.event is not None
    await env.give.execute(me, BHUJA)  # another device
    with pytest.raises(ProgressionChanged):
        await env.give.execute(me, KURMASANA, expected=start.event.id)
    with pytest.raises(ProgressionChanged):
        await env.set.execute(me, SETU, expected=None)
    assert len((await env.repo.get(me.account.id)).events) == 2


async def test_a_lost_compare_and_set_raises() -> None:
    env, me = Env(), _me()
    await env.set.execute(me, NAVASANA)

    async def racing(*_: object, **__: object) -> None:
        return None

    env.repo.apply = racing  # type: ignore[method-assign]
    with pytest.raises(ProgressionChanged):
        await env.give.execute(me, BHUJA)


async def test_undo_only_the_latest_then_a_give_celebrates_again() -> None:
    env, me = Env(), _me()
    start = await env.set.execute(me, NAVASANA)
    given = await env.give.execute(me, BHUJA)
    assert start.event is not None
    assert given.event is not None
    with pytest.raises(NotLatest):
        await env.undo.execute(me, start.event.id)
    view = await env.undo.execute(me, given.event.id)
    assert view.progression is not None
    assert view.progression.position == NAVASANA
    again = await env.give.execute(me, BHUJA)
    assert again.celebrations[0].kind is CelebrationKind.NEW_ASANA


async def test_undoing_the_start_unsets() -> None:
    env, me = Env(), _me()
    start = await env.set.execute(me, NAVASANA)
    assert start.event is not None
    view = await env.undo.execute(me, start.event.id)
    assert view.progression is None


async def test_given_again_after_a_change_back_is_quiet() -> None:
    env, me = Env(), _me()
    await env.set.execute(me, SETU)
    await env.give.execute(me, PASASANA)
    await env.set.execute(me, SETU)  # back to full Primary (injury)
    again = await env.give.execute(me, PASASANA)
    assert again.event is not None
    assert again.celebrations == ()


async def test_items_celebrate_once_and_need_a_position() -> None:
    env, me = Env(), _me()
    with pytest.raises(ProgressionNotSet):
        await env.item.execute(me, "drop-backs", True)
    await env.set.execute(me, SETU)
    first = await env.item.execute(me, "drop-backs", True)
    assert first.celebrations == (Celebration(CelebrationKind.ITEM, key="drop-backs"),)
    assert (await env.item.execute(me, "drop-backs", True)).event is None
    await env.item.execute(me, "drop-backs", False)
    again = await env.item.execute(me, "drop-backs", True)
    assert again.celebrations == ()


async def test_dates_follow_the_logging_rules_in_the_callers_zone() -> None:
    env, me = Env(), _me()
    await env.set.execute(me, NAVASANA, on=MON)
    with pytest.raises(DateInFuture):
        await env.give.execute(me, BHUJA, on=TUE + timedelta(days=1))
    with pytest.raises(DateTooEarly):
        await env.give.execute(me, BHUJA, on=date(1999, 12, 31))
    # 23:30 UTC on Oct 27: already Oct 28 in Kiritimati (UTC+14), still Oct 27 in Honolulu.
    late = datetime(2026, 10, 27, 23, 30, tzinfo=UTC)
    kiritimati = await Env(late).set.execute(_me("Pacific/Kiritimati"), NAVASANA)
    honolulu = await Env(late).set.execute(_me("Pacific/Honolulu"), NAVASANA)
    assert kiritimati.event is not None
    assert honolulu.event is not None
    assert kiritimati.event.occurred_on == date(2026, 10, 28)
    assert honolulu.event.occurred_on == date(2026, 10, 27)


async def test_get_suggests_a_start_only_while_unset() -> None:
    env, me = Env(), _me()
    await env.days.upsert(me.account.id, DayLog(MON, DayStatus.PRACTICED), "Asia/Almaty")
    env.days.practice_rows[(me.account.id, MON)] = Practice(
        context=PracticeContext.MYSORE, length=PracticeLength(("primary",), "navasana")
    )
    unset = await env.get.execute(me)
    assert unset.suggested == NAVASANA
    assert unset.today == TUE
    await env.set.execute(me, KURMASANA)
    env.repo.calls.clear()
    set_ = await env.get.execute(me)
    assert set_.suggested is None
    assert env.repo.calls == ["get"]


async def test_not_new_is_stored_for_the_current_position() -> None:
    env, me = Env(), _me()
    await env.dismiss.execute(me, KURMASANA)  # unset: nothing
    await env.set.execute(me, NAVASANA)
    await env.dismiss.execute(me, KURMASANA)
    view = await env.repo.get(me.account.id)
    assert view.progression is not None
    assert view.progression.dismissed == KURMASANA


def test_progression_is_owner_only() -> None:
    me, other = _me().account, _me().account
    assert policies.can_view_progression(me, me)
    assert not policies.can_view_progression(other, me)


# Practice save hint and presets


async def _practiced(env: Env, me: Principal, day: date = TUE) -> None:
    await env.days.upsert(me.account.id, DayLog(day, DayStatus.PRACTICED), "Asia/Almaty")


async def test_save_hints_a_new_asana_only_when_the_length_changes() -> None:
    env, me = Env(), _me()
    save = SavePractice(env.practices, catalog(), track())
    await _practiced(env, me)
    await env.set.execute(me, NAVASANA)
    await save.execute(me, TUE, PracticePatch.of(context=PracticeContext.MYSORE))
    beyond = PracticeLength(("primary",), "kurmasana")
    saved = await save.execute(me, TUE, PracticePatch.of(length=beyond))
    assert saved.new_asana_hint == KURMASANA
    duration = await save.execute(me, TUE, PracticePatch.of(duration_min=90))
    assert duration.new_asana_hint is None  # not a length tap


async def test_save_never_hints_for_self_practice_or_when_dismissed() -> None:
    env, me = Env(), _me()
    save = SavePractice(env.practices, catalog(), track())
    await _practiced(env, me)
    await env.set.execute(me, NAVASANA)
    beyond = PracticeLength(("primary",), "kurmasana")
    await save.execute(me, TUE, PracticePatch.of(context=PracticeContext.SELF))
    assert (await save.execute(me, TUE, PracticePatch.of(length=beyond))).new_asana_hint is None
    await save.execute(me, TUE, PracticePatch.of(context=PracticeContext.MYSORE, length=None))
    await env.dismiss.execute(me, KURMASANA)
    assert (await save.execute(me, TUE, PracticePatch.of(length=beyond))).new_asana_hint is None


async def test_presets_put_my_practice_first_and_cap_recents() -> None:
    env, me = Env(), _me()
    presets = GetPracticePresets(env.practices, catalog(), track())
    await env.set.execute(me, Position("intermediate", "pincha-mayurasana"))
    for i, end in enumerate(["ustrasana", "kurmasana", "marichyasana-d", "bhekasana"]):
        day = MON - timedelta(days=i)
        await _practiced(env, me, day)
        series = ("primary", "intermediate") if end in ("ustrasana", "bhekasana") else ("primary",)
        env.days.practice_rows[(me.account.id, day)] = Practice(length=PracticeLength(series, end))
    found = await presets.execute(me, TUE)
    kinds = [k for k, _ in found.presets]
    assert kinds == ["short", "half_primary", "full_primary", "mine", "mine", "recent"]
    mine = [length for k, length in found.presets if k == "mine"]
    assert mine == [
        PracticeLength(("primary", "intermediate"), "pincha-mayurasana"),
        PracticeLength(("intermediate",), "pincha-mayurasana"),
    ]


async def test_a_mis_tapped_forward_change_undone_leaves_no_trace() -> None:
    env, me = Env(), _me()
    await env.set.execute(me, NAVASANA)
    wrong = await env.set.execute(me, SETU)  # meant Bhujapidasana
    assert wrong.event is not None
    await env.undo.execute(me, wrong.event.id)
    real = await env.give.execute(me, BHUJA)
    assert real.celebrations[0].kind is CelebrationKind.NEW_ASANA
