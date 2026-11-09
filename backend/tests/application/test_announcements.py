"""Announcements' policies, use cases and tick step on in-memory ports (NT-03, spec §3, §8,
ADR-0038). A frozen clock throughout."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from tests.announcement_fakes import T0, InMemoryAnnouncements
from tests.fakes import (
    FakeCalculator,
    FakeNotifier,
    FixedClock,
    InMemoryAccounts,
    InMemoryMoon,
    InMemoryNotifications,
)
from tests.teacher_link_fakes import add_person
from tristhana.application.announcements import (
    DeleteAnnouncement,
    GetAnnouncements,
    GetSentAnnouncements,
    MuteAnnouncements,
    PinAnnouncement,
    SendAnnouncement,
    Target,
)
from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_announce_to_shala,
    can_manage_announcement,
)
from tristhana.application.ports.notifications import (
    Announcement,
    DeliveryResult,
    DeliveryStatus,
    PracticeReminder,
)
from tristhana.application.tick import RunTick
from tristhana.domain.accounts import Account
from tristhana.domain.announcements import (
    AnnouncementLimit,
    InvalidAnnouncement,
    Source,
    SourceKind,
)
from tristhana.domain.moon import Cities
from tristhana.domain.notifications import (
    DEFAULTS,
    MoonReminders,
    NotificationSettings,
    PracticeReminders,
)
from tristhana.domain.shalas import Membership, ShalaRole

NOW = datetime(2026, 11, 9, 5, 0, tzinfo=UTC)  # 10:00 in Almaty
R = ShalaRole


def _account(uid: UUID, name: str = "Anna") -> Account:
    return Account(uid, name, "en", "Asia/Almaty", NOW)


def _p(uid: UUID) -> Principal:
    return Principal(_account(uid))


class World:
    def __init__(self, now: datetime = NOW) -> None:
        self.clock = FixedClock(now)
        self.repo = InMemoryAnnouncements(self.clock)
        self.send = SendAnnouncement(self.repo, self.clock)
        self.feed = GetAnnouncements(self.repo, self.clock)
        self.sent = GetSentAnnouncements(self.repo, self.clock)
        self.pin = PinAnnouncement(self.repo, self.clock)
        self.delete = DeleteAnnouncement(self.repo)
        self.mute = MuteAnnouncements(self.repo)


# --- policies -------------------------------------------------------------------------


def _m(*, owner: bool = False, roles: frozenset[R] = frozenset(), student: bool = False):
    return Membership(uuid4(), owner, roles, student)


@pytest.mark.parametrize(
    ("member", "allowed"),
    [
        (_m(owner=True), True),
        (_m(roles=frozenset({R.ADMIN})), True),
        (_m(roles=frozenset({R.TEACHER})), True),
        (_m(roles=frozenset({R.OFFICE})), True),
        (_m(roles=frozenset({R.ASSISTANT})), False),
        (_m(student=True), False),
        (None, False),
    ],
)
def test_who_announces_to_a_shala(member: Membership | None, allowed: bool) -> None:
    assert can_announce_to_shala(member) is allowed


def test_who_manages_an_announcement() -> None:
    me, other = uuid4(), uuid4()
    a = _account(me)
    assert can_manage_announcement(a, me, None)
    assert not can_manage_announcement(a, other, None)
    assert can_manage_announcement(a, other, _m(owner=True))
    assert can_manage_announcement(a, other, _m(roles=frozenset({R.ADMIN})))
    assert not can_manage_announcement(a, other, _m(roles=frozenset({R.TEACHER, R.OFFICE})))
    assert not can_manage_announcement(a, other, _m(student=True))


# --- send ------------------------------------------------------------------------------


async def test_a_teacher_sends_to_all_their_students_and_nothing_is_pushed() -> None:
    w = World()
    t, s1, s2 = w.repo.person("Anna"), w.repo.person("B"), w.repo.person("C")
    w.repo.link(s1, t)
    w.repo.link(s2, t)
    w.repo.links[(s2, t)].muted = True
    item = await w.send.execute(_p(t), Target(), "  Mysore closed Mon 10 Nov  ", 0)
    assert item.text == "Mysore closed Mon 10 Nov"
    assert item.audience == 2  # muted people count too (Q172)
    assert item.source == Source(SourceKind.TEACHER, t)
    assert item.pinned_until is None
    assert w.repo.calls == ["create"]


async def test_the_fourth_in_24_hours_is_refused_until_one_is_deleted() -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    sent = [await w.send.execute(_p(t), Target(), f"note {i}", 0) for i in range(3)]
    with pytest.raises(AnnouncementLimit):
        await w.send.execute(_p(t), Target(), "fourth", 0)
    await w.delete.execute(_p(t), sent[1].id)  # a typo: delete and send again (Q173)
    again = await w.send.execute(_p(t), Target(), "fixed", 0)
    assert again.text == "fixed"


async def test_the_limit_rolls_after_24_hours() -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    for i in range(3):
        await w.send.execute(_p(t), Target(), f"note {i}", 0)
    w.clock.instant = NOW + timedelta(hours=24, seconds=1)
    await w.send.execute(_p(t), Target(), "next day", 0)


async def test_the_limit_is_per_source() -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    shala = w.repo.shala("Ashtanga Almaty", t)
    w.repo.student(shala, s)
    for i in range(3):
        await w.send.execute(_p(t), Target(), f"note {i}", 0)
    await w.send.execute(_p(t), Target(shala), "to the shala", 0)


@pytest.mark.parametrize("text", ["", "   \n ", "a" * 1001])
async def test_invalid_text(text: str) -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    with pytest.raises(InvalidAnnouncement):
        await w.send.execute(_p(t), Target(), text, 0)
    assert w.repo.calls == []


async def test_an_unknown_pin_length_is_invalid() -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    with pytest.raises(InvalidAnnouncement):
        await w.send.execute(_p(t), Target(), "hello", 14)


async def test_no_students_is_invalid() -> None:
    w = World()
    t = w.repo.person("Anna")
    with pytest.raises(InvalidAnnouncement):
        await w.send.execute(_p(t), Target(), "hello", 0)
    assert w.repo.rows == {}


async def test_shala_roles_who_may_send() -> None:
    w = World()
    owner, manager, teacher, desk, assistant, student, outsider = (
        w.repo.person(n) for n in ("O", "M", "T", "D", "A", "S", "X")
    )
    shala = w.repo.shala("Ashtanga Almaty", owner)
    w.repo.staff(shala, manager, R.ADMIN)
    w.repo.staff(shala, teacher, R.TEACHER)
    w.repo.staff(shala, desk, R.OFFICE)
    w.repo.staff(shala, assistant, R.ASSISTANT)
    w.repo.student(shala, student)
    w.clock.instant = NOW
    for who in (owner, manager, teacher):
        await w.send.execute(_p(who), Target(shala), "hello", 0)
    w.clock.instant = NOW + timedelta(days=2)  # past the rate limit
    await w.send.execute(_p(desk), Target(shala), "hello", 0)
    for who in (assistant, student):
        with pytest.raises(NotAllowed):
            await w.send.execute(_p(who), Target(shala), "hello", 0)
    with pytest.raises(NotFound):
        await w.send.execute(_p(outsider), Target(shala), "hello", 0)
    with pytest.raises(NotFound):
        await w.send.execute(_p(owner), Target(uuid4()), "hello", 0)


async def test_the_shala_audience_is_everyone_but_the_author() -> None:
    w = World()
    owner, desk, s1, s2 = (w.repo.person(n) for n in ("O", "D", "S1", "S2"))
    shala = w.repo.shala("Ashtanga Almaty", owner)
    w.repo.staff(shala, desk, R.OFFICE)
    w.repo.student(shala, s1)
    w.repo.student(shala, s2)
    item = await w.send.execute(_p(desk), Target(shala), "Closed 1-20 August", 7)
    assert item.audience == 3  # the owner and both students
    assert item.shala_name == "Ashtanga Almaty"
    assert item.pinned_until == NOW + timedelta(days=7)


async def test_a_new_pin_unpins_only_the_same_sources_earlier_one() -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    shala = w.repo.shala("Ashtanga Almaty", t)
    w.repo.student(shala, s)
    first = await w.send.execute(_p(t), Target(), "one", 7)
    other = await w.send.execute(_p(t), Target(shala), "shala", 30)
    second = await w.send.execute(_p(t), Target(), "two", 30)
    assert w.repo.rows[first.id].pinned_until is None
    assert w.repo.rows[other.id].pinned_until == NOW + timedelta(days=30)
    assert w.repo.rows[second.id].pinned_until == NOW + timedelta(days=30)


# --- feed, sent, pin, delete, mute ------------------------------------------------------


async def test_the_feed_has_pins_first_then_newest_within_30_days() -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    w.clock.instant = NOW - timedelta(days=40)
    old_pinned = await w.send.execute(_p(t), Target(), "old but pinned", 30)
    w.clock.instant = NOW - timedelta(days=35)
    await w.send.execute(_p(t), Target(), "too old", 0)
    w.clock.instant = NOW - timedelta(days=2)
    older = await w.send.execute(_p(t), Target(), "older", 0)
    w.clock.instant = NOW - timedelta(days=1)
    newer = await w.send.execute(_p(t), Target(), "newer", 0)
    # the 40-day-old pin expired after 30 days: re-pin it now for a month
    w.clock.instant = NOW
    await w.pin.execute(_p(t), old_pinned.id, 30)
    feed = await w.feed.execute(_p(s))
    assert [i.id for i in feed.items] == [old_pinned.id, newer.id, older.id]
    assert feed.items[0].pinned_until is not None
    assert feed.items[1].pinned_until is None
    assert feed.items[1].author_name == "Anna"
    assert feed.items[1].can_manage is False


async def test_newcomers_see_items_from_before_they_joined() -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    item = await w.send.execute(_p(t), Target(), "closed in August", 0)
    late = w.repo.person("C")
    w.repo.link(late, t, at=NOW + timedelta(hours=1))
    feed = await w.feed.execute(_p(late))
    assert [i.id for i in feed.items] == [item.id]


async def test_a_foreign_source_is_not_found() -> None:
    w = World()
    t, s, co = w.repo.person("Anna"), w.repo.person("B"), w.repo.person("C")
    w.repo.link(s, t)
    with pytest.raises(NotFound):
        await w.feed.execute(_p(co), Source(SourceKind.TEACHER, t))
    # the teacher's own teacher (one hop, one way) and a reversed link can't read it either
    with pytest.raises(NotFound):
        await w.feed.execute(_p(t), Source(SourceKind.TEACHER, s))


async def test_a_removed_author_loses_their_name_on_the_feed() -> None:
    w = World()
    owner, desk, s = w.repo.person("O"), w.repo.person("Desk"), w.repo.person("S")
    shala = w.repo.shala("Ashtanga Almaty", owner)
    w.repo.staff(shala, desk, R.OFFICE)
    w.repo.student(shala, s)
    await w.send.execute(_p(desk), Target(shala), "hello", 0)
    del w.repo.members[(shala, desk)]
    feed = await w.feed.execute(_p(s))
    assert feed.items[0].author_name is None
    assert feed.items[0].source_name == "Ashtanga Almaty"


async def test_sent_lists_only_my_own() -> None:
    w = World()
    owner, desk, s = w.repo.person("O"), w.repo.person("Desk"), w.repo.person("S")
    shala = w.repo.shala("Ashtanga Almaty", owner)
    w.repo.staff(shala, desk, R.OFFICE)
    w.repo.student(shala, s)
    mine = await w.send.execute(_p(owner), Target(shala), "mine", 0)
    await w.send.execute(_p(desk), Target(shala), "theirs", 0)
    assert [i.id for i in await w.sent.execute(_p(owner))] == [mine.id]


async def test_a_manager_moderates_but_a_shala_teacher_does_not() -> None:
    w = World()
    owner, manager, teacher, desk, s = (w.repo.person(n) for n in ("O", "M", "T", "D", "S"))
    shala = w.repo.shala("Ashtanga Almaty", owner)
    w.repo.staff(shala, manager, R.ADMIN)
    w.repo.staff(shala, teacher, R.TEACHER)
    w.repo.staff(shala, desk, R.OFFICE)
    w.repo.student(shala, s)
    item = await w.send.execute(_p(desk), Target(shala), "hello", 0)
    with pytest.raises(NotAllowed):
        await w.delete.execute(_p(teacher), item.id)
    with pytest.raises(NotAllowed):
        await w.pin.execute(_p(s), item.id, 7)
    pinned = await w.pin.execute(_p(manager), item.id, 7)
    assert pinned.pinned_until == NOW + timedelta(days=7)
    await w.delete.execute(_p(manager), item.id)
    await w.delete.execute(_p(manager), item.id)  # idempotent
    assert w.repo.rows == {}


async def test_a_stranger_cannot_touch_an_item() -> None:
    w = World()
    t, s, x = w.repo.person("Anna"), w.repo.person("B"), w.repo.person("X")
    w.repo.link(s, t)
    item = await w.send.execute(_p(t), Target(), "hello", 0)
    with pytest.raises(NotFound):
        await w.pin.execute(_p(x), item.id, 7)
    await w.delete.execute(_p(x), item.id)  # looks like "already gone"
    assert item.id in w.repo.rows
    with pytest.raises(NotAllowed):
        await w.delete.execute(_p(s), item.id)  # a student can see it, but not delete it


async def test_unpin() -> None:
    w = World()
    t, s = w.repo.person("Anna"), w.repo.person("B")
    w.repo.link(s, t)
    item = await w.send.execute(_p(t), Target(), "hello", 7)
    assert (await w.pin.execute(_p(t), item.id, 0)).pinned_until is None


async def test_mute_is_keyed_on_the_caller() -> None:
    w = World()
    t, s, x = w.repo.person("Anna"), w.repo.person("B"), w.repo.person("X")
    w.repo.link(s, t)
    await w.mute.execute(_p(s), Source(SourceKind.TEACHER, t), True)
    assert w.repo.links[(s, t)].muted
    with pytest.raises(NotFound):
        await w.mute.execute(_p(x), Source(SourceKind.TEACHER, t), True)
    feed = await w.feed.execute(_p(s))
    assert feed.sources[0].muted is True
    await w.mute.execute(_p(s), Source(SourceKind.TEACHER, t), False)
    assert not w.repo.links[(s, t)].muted


# --- the tick ---------------------------------------------------------------------------


class Tick:
    def __init__(self, now: datetime = NOW) -> None:
        self.w = World(now)
        self.accounts = InMemoryAccounts()
        self.notifications = InMemoryNotifications(self.accounts)
        self.w.repo.deliveries = self.notifications.deliveries
        self.notifier = FakeNotifier()

    def run_tick(self) -> RunTick:
        return RunTick(
            self.w.clock,
            _cities(),
            InMemoryMoon(),
            FakeCalculator(),
            self.notifications,
            self.notifier,
            announcements=self.w.repo,
        )

    async def run(self) -> None:
        await self.run_tick().execute(timedelta(seconds=30))

    @property
    def pushed(self) -> list[tuple[str, Announcement]]:
        return [
            (r.telegram_id, n) for r, n in self.notifier.delivered if isinstance(n, Announcement)
        ]


def _cities() -> Cities:
    from tests.application.test_moon_tick import CITIES

    return CITIES


async def test_the_tick_pushes_to_the_live_audience_at_send_time() -> None:
    k = Tick()
    w = k.w
    t = w.repo.person("Anna")
    s = w.repo.person("B", telegram_id="1")
    muted = w.repo.person("C", telegram_id="2")
    off = w.repo.person("D", telegram_id="3", announcements_on=False)
    gone = w.repo.person("E", telegram_id="4", unreachable=True)
    for who in (s, muted, off, gone):
        w.repo.link(who, t)
    w.repo.links[(muted, t)].muted = True
    item = await w.send.execute(_p(t), Target(), "Led class Sun 15 Nov, 7:00", 0)
    late = w.repo.person("F", telegram_id="5")
    w.repo.link(late, t, at=NOW + timedelta(minutes=1))
    w.clock.instant = NOW + timedelta(minutes=5)
    await k.run()
    assert [tid for tid, _ in k.pushed] == ["1"]
    n = k.pushed[0][1]
    assert (n.id, n.text, n.source_name, n.author_name) == (
        item.id,
        "Led class Sun 15 Nov, 7:00",
        "Anna",
        "Anna",
    )
    assert n.silent is False
    await k.run()  # a second tick sends no duplicates
    assert len(k.pushed) == 1


async def test_quiet_hours_send_now_silently_and_others_with_sound() -> None:
    at = datetime(2026, 11, 9, 0, 30, tzinfo=UTC)  # 05:30 Almaty, 01:30 Berlin, 16:30 LA
    k = Tick(at)
    w = k.w
    t = w.repo.person("Anna")
    early = w.repo.person("B", telegram_id="1", zone="Asia/Almaty")
    awake = w.repo.person("C", telegram_id="2", zone="America/Los_Angeles")
    nozone = w.repo.person("D", telegram_id="3", zone=None)
    for who in (early, awake, nozone):
        w.repo.link(who, t)
    await w.send.execute(_p(t), Target(), "No Mysore today: power cut", 0)
    await k.run()
    by = {tid: n for tid, n in k.pushed}
    assert by["1"].silent is True
    assert by["1"].local_date == date(2026, 11, 9)
    assert by["2"].silent is False
    assert by["2"].local_date == date(2026, 11, 8)
    assert by["3"].silent is True


async def test_a_stale_announcement_is_never_pushed() -> None:
    k = Tick()
    w = k.w
    t, s = w.repo.person("Anna"), w.repo.person("B", telegram_id="1")
    w.repo.link(s, t)
    await w.send.execute(_p(t), Target(), "hello", 0)
    w.clock.instant = NOW + timedelta(hours=25)
    await k.run()
    assert k.pushed == []


async def test_a_blocked_recipient_is_marked_unreachable() -> None:
    k = Tick()
    w = k.w
    t, s = w.repo.person("Anna"), w.repo.person("B", telegram_id="1")
    w.repo.link(s, t)
    await w.send.execute(_p(t), Target(), "hello", 0)
    k.notifier.outcomes.append(DeliveryResult(DeliveryStatus.BLOCKED))
    await k.run()
    assert s in k.notifications.unreachable


async def test_retry_after_stops_the_run_and_the_next_tick_resumes() -> None:
    k = Tick()
    w = k.w
    t = w.repo.person("Anna")
    ss = [w.repo.person(n, telegram_id=str(i)) for i, n in enumerate("BCD")]
    for s in ss:
        w.repo.link(s, t)
    await w.send.execute(_p(t), Target(), "hello", 0)
    k.notifier.outcomes.extend(
        [DeliveryResult(DeliveryStatus.SENT), DeliveryResult(DeliveryStatus.RETRY_AFTER, 3.0)]
    )
    tick = k.run_tick()
    result = await tick.execute(timedelta(seconds=30))
    assert result.stopped_early
    assert result.announced == 1
    await k.run()
    pushed = [tid for tid, _ in k.pushed]
    assert len(pushed) == 4  # the rate-limited one was retried once
    assert set(pushed) == {"0", "1", "2"}


async def test_the_deadline_is_respected() -> None:
    k = Tick()
    w = k.w
    t, s = w.repo.person("Anna"), w.repo.person("B", telegram_id="1")
    w.repo.link(s, t)
    await w.send.execute(_p(t), Target(), "hello", 0)
    result = await k.run_tick().execute(timedelta(0))
    assert result.stopped_early
    assert k.pushed == []


async def _capped(announce: bool) -> Tick:
    k = Tick(datetime(2026, 11, 9, 4, 0, tzinfo=UTC))  # 09:00 Almaty
    w = k.w
    student = add_person(k.accounts, "1", "B", zone="Asia/Almaty")
    w.repo.people[student.id] = w.repo.people.pop(w.repo.person("B", telegram_id="1"))
    t = w.repo.person("Anna")
    w.repo.link(student.id, t)
    practice = PracticeReminders(True, time(10), frozenset(range(1, 8)))
    k.notifications.stored[student.id] = NotificationSettings(
        MoonReminders(frozenset(), time(19)), DEFAULTS.quiet, 1, practice
    )
    if announce:
        await w.send.execute(_p(t), Target(), "hello", 0)
    await k.run()
    w.clock.instant = datetime(2026, 11, 9, 5, 5, tzinfo=UTC)  # 10:05: the practice slot
    await k.run()
    return k


async def test_an_announcement_ignores_the_cap_but_counts_toward_it() -> None:
    with_note = await _capped(announce=True)
    assert len(with_note.pushed) == 1  # the cap is 1, yet it went
    assert not any(isinstance(n, PracticeReminder) for _, n in with_note.notifier.delivered)
    control = await _capped(announce=False)
    assert any(isinstance(n, PracticeReminder) for _, n in control.notifier.delivered)


async def test_nothing_but_the_push_changes_after_a_closure_note() -> None:
    k = Tick()
    w = k.w
    t, s = w.repo.person("Anna"), w.repo.person("B", telegram_id="1")
    w.repo.link(s, t)
    await w.send.execute(_p(t), Target(), "Shala closed Mon 10 Nov (moon day)", 0)
    await k.run()
    assert k.notifications.stored == {}
    assert k.accounts.accounts == {}
    assert set(k.notifications.deliveries) == {(s, f"ann:{next(iter(w.repo.rows))}")}


async def test_prune_after_90_days() -> None:
    k = Tick()
    w = k.w
    t, s = w.repo.person("Anna"), w.repo.person("B", telegram_id="1")
    w.repo.link(s, t)
    w.clock.instant = NOW - timedelta(days=91)
    await w.send.execute(_p(t), Target(), "old", 0)
    w.clock.instant = NOW
    await w.send.execute(_p(t), Target(), "new", 0)
    result = await k.run_tick().execute(timedelta(seconds=30))
    assert [r.text for r in w.repo.rows.values()] == ["new"]
    assert result.pruned >= 1


def test_t0_is_before_now() -> None:
    assert T0 < NOW


async def test_an_ex_author_can_delete_but_not_pin() -> None:
    w = World()
    owner, desk, s = w.repo.person("O"), w.repo.person("Desk"), w.repo.person("S")
    shala = w.repo.shala("Ashtanga Almaty", owner)
    w.repo.staff(shala, desk, R.OFFICE)
    w.repo.student(shala, s)
    item = await w.send.execute(_p(desk), Target(shala), "hello", 0)
    del w.repo.members[(shala, desk)]
    with pytest.raises(NotAllowed):  # the author sees it, but no longer speaks for the shala
        await w.pin.execute(_p(desk), item.id, 30)
    await w.delete.execute(_p(desk), item.id)
    assert w.repo.rows == {}


async def test_a_shala_teacher_who_is_now_an_assistant_cannot_pin_their_own() -> None:
    w = World()
    owner, t, s = w.repo.person("O"), w.repo.person("T"), w.repo.person("S")
    shala = w.repo.shala("Ashtanga Almaty", owner)
    w.repo.staff(shala, t, R.TEACHER)
    w.repo.student(shala, s)
    item = await w.send.execute(_p(t), Target(shala), "hello", 0)
    w.repo.staff(shala, t, R.ASSISTANT)
    with pytest.raises(NotAllowed):
        await w.pin.execute(_p(t), item.id, 7)
