"""The teacher view's use cases on a scripted port (ST-06, spec §3, §6, §8): each student's own
today, the read ranges, the provisional zone, the policy as a second gate, the quiet note and its
consent flag, and what stops at the use case. A frozen clock throughout. Then the policies."""

import inspect
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from tests.fakes import FixedClock, InMemoryAccounts
from tests.teacher_link_fakes import InMemoryTeacherLinks, add_person
from tests.teacher_view_fakes import ScriptedTeacherView
from tristhana.application.policies import (
    NotAllowed,
    Principal,
    can_view_activity,
    can_view_check_ins,
    can_view_diary,
    can_view_last_asana,
    can_view_milestones,
    can_view_progression,
)
from tristhana.application.ports.teacher_links import NotLinked
from tristhana.application.ports.teacher_view import (
    SharedDetail,
    SharedLog,
    SharedPage,
    StudentLink,
)
from tristhana.application.teacher_view import GetStudent, GetStudents
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.practice import PracticeLength
from tristhana.domain.progression import STANDING_ONLY, Position
from tristhana.domain.teacher_view import DayCell, SharedDay, StudentCard, StudentToday

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
UTC_TODAY = date(2026, 11, 7)
LINKED = date(2026, 1, 1)
P, R = SharedDay.PRACTICED, SharedDay.REST
LENGTH = PracticeLength(("primary",), "navasana")
ZONES = [
    "Asia/Kolkata",
    "Asia/Kathmandu",
    "Europe/Berlin",
    "Asia/Almaty",
    "Europe/Moscow",
    "America/New_York",
]


def _day(n: int) -> date:
    return UTC_TODAY + timedelta(days=n)


@dataclass
class World:
    instant: datetime = NOW
    clock: FixedClock = field(init=False)
    accounts: InMemoryAccounts = field(init=False)
    repo: ScriptedTeacherView = field(init=False)
    teacher: Account = field(init=False)
    _ids: int = 100

    def __post_init__(self) -> None:
        self.clock = FixedClock(self.instant)
        self.accounts = InMemoryAccounts(clock=self.clock)
        self.repo = ScriptedTeacherView()
        self.teacher = add_person(self.accounts, "1", "Лена", "ru", "Pacific/Kiritimati")

    def link(
        self,
        name: str | None = "Anna",
        zone: str | None = "Asia/Almaty",
        locale: Locale = "en",
        linked_on: date = LINKED,
        teacher: UUID | None = None,
    ) -> StudentLink:
        return StudentLink(
            teacher_id=teacher or self.teacher.id,
            student_id=uuid4(),
            name=name,
            timezone=zone,
            locale=locale,
            linked_on=linked_on,
        )

    def listed(self, link: StudentLink, shown: dict[date, SharedDay] | None = None) -> None:
        self.repo.logs.append(SharedLog(link, shown or {}))

    def detailed(
        self,
        link: StudentLink,
        shown: dict[date, SharedDay] | None = None,
        lengths: dict[date, PracticeLength] | None = None,
        position: Position | None = None,
        agreed: bool = True,
    ) -> UUID:
        log = SharedLog(link, shown or {})
        self.repo.details[link.student_id] = SharedDetail(log, lengths or {}, position, agreed)
        return link.student_id

    async def students(self, offset: int = 0, limit: int = 20) -> tuple[list[StudentToday], int]:
        use_case = GetStudents(self.repo, self.clock)
        found, total = await use_case.execute(Principal(self.teacher), offset, limit)
        return list(found), total

    async def card(self, student: UUID) -> StudentCard:
        return await GetStudent(self.repo, self.clock).execute(Principal(self.teacher), student)


@pytest.fixture
def world() -> World:
    return World()


def _midnight(day: date, zone: str) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(zone)).astimezone(UTC)


# Built with the port and the clock only (ADR-0031)


@pytest.mark.parametrize("use_case", [GetStudents, GetStudent])
def test_a_use_case_takes_the_port_and_the_clock_and_nothing_else(use_case: type) -> None:
    parameters = list(inspect.signature(use_case).parameters)

    assert len(parameters) == 2


# Each student's own today


@pytest.mark.parametrize(
    ("instant", "honolulu", "kiritimati"),
    [
        (datetime(2026, 11, 7, 9, 30, tzinfo=UTC), date(2026, 11, 6), date(2026, 11, 7)),
        (datetime(2026, 11, 7, 10, 30, tzinfo=UTC), date(2026, 11, 7), date(2026, 11, 8)),
        (datetime(2026, 11, 7, 23, 30, tzinfo=UTC), date(2026, 11, 7), date(2026, 11, 8)),
    ],
    ids=["0930", "1030", "2330"],
)
async def test_kiritimati_and_honolulu_each_get_their_own_today_on_one_instant(
    instant: datetime, honolulu: date, kiritimati: date
) -> None:
    world = World(instant)
    # Each student logged only their own today, and the other's today is the other state.
    west = {honolulu: P, kiritimati: R} if honolulu != kiritimati else {honolulu: P}
    east = {kiritimati: P, honolulu: R} if honolulu != kiritimati else {kiritimati: P}
    world.listed(world.link("A", "Pacific/Honolulu"), west)
    world.listed(world.link("B", "Pacific/Kiritimati"), east)

    found, _ = await world.students()

    assert [s.today for s in found] == [P, P]


async def test_the_list_reads_the_three_dates_that_can_be_someones_today(world: World) -> None:
    await world.students(40, 10)

    assert world.repo.page_calls == [(world.teacher.id, 40, 10, _day(-1), _day(1))]


@pytest.mark.parametrize(
    ("hour", "zone"),
    [(9, "Pacific/Honolulu"), (11, "Pacific/Kiritimati")],
    ids=["a-day-behind", "a-day-ahead"],
)
async def test_the_list_range_reaches_both_ends_of_the_earth(hour: int, zone: str) -> None:
    world = World(datetime(2026, 11, 7, hour, tzinfo=UTC))
    today = world.instant.astimezone(ZoneInfo(zone)).date()
    assert today != UTC_TODAY
    world.listed(world.link(zone=zone), {today: R})

    found, _ = await world.students()

    assert found[0].today is R


async def test_the_card_reads_21_days_back_and_one_ahead_of_utc(world: World) -> None:
    student = world.detailed(world.link())

    await world.card(student)

    assert world.repo.student_calls == [(world.teacher.id, student, _day(-21), _day(1))]


@pytest.mark.parametrize(
    ("instant", "zone", "today"),
    [
        (datetime(2026, 11, 7, 9, tzinfo=UTC), "Pacific/Honolulu", date(2026, 11, 6)),
        (datetime(2026, 11, 7, 11, tzinfo=UTC), "Pacific/Kiritimati", date(2026, 11, 8)),
    ],
    ids=["honolulu", "kiritimati"],
)
async def test_the_card_ends_on_the_students_today(
    instant: datetime, zone: str, today: date
) -> None:
    world = World(instant)
    student = world.detailed(world.link(zone=zone), {today: P}, {today: LENGTH})

    card = await world.card(student)

    assert card.days[-1] == DayCell(today, P, LENGTH)
    assert [d.date for d in card.days] == [today - timedelta(days=n) for n in range(6, -1, -1)]


async def test_honolulu_a_day_behind_still_finds_a_shown_day_20_days_back() -> None:
    """The oldest date of the range matters only here: `utc_today - 21` is its today - 20."""
    world = World(datetime(2026, 11, 7, 9, tzinfo=UTC))
    today = date(2026, 11, 6)
    student = world.detailed(world.link(zone="Pacific/Honolulu"), {today - timedelta(days=20): R})

    assert (await world.card(student)).quiet is False


async def test_kiritimati_a_day_ahead_gets_the_note_21_days_after_its_last_shown_day() -> None:
    world = World(datetime(2026, 11, 7, 11, tzinfo=UTC))
    today = date(2026, 11, 8)
    student = world.detailed(world.link(zone="Pacific/Kiritimati"), {today - timedelta(days=21): R})

    assert (await world.card(student)).quiet is True


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize(
    "midnight",
    [date(2026, 11, 8), date(2026, 3, 29), date(2026, 10, 25), date(2026, 3, 8)],
    ids=["plain", "berlin-spring", "berlin-autumn", "new-york-spring"],
)
async def test_today_flips_at_the_students_own_midnight(zone: str, midnight: date) -> None:
    before, after = midnight - timedelta(days=1), midnight
    at = _midnight(midnight, zone)
    shown = {before: P, after: R}

    for instant, expected in ((at - timedelta(seconds=1), P), (at, R)):
        world = World(instant)
        world.listed(world.link(zone=zone), shown)

        found, _ = await world.students()

        assert found[0].today is expected, instant


@pytest.mark.parametrize(
    ("locale", "instant", "expected"),
    [
        ("ru", datetime(2026, 11, 7, 21, 30, tzinfo=UTC), date(2026, 11, 8)),  # Moscow, UTC+3
        ("en", datetime(2026, 11, 7, 21, 30, tzinfo=UTC), date(2026, 11, 7)),  # UTC
    ],
)
async def test_an_unknown_zone_uses_the_provisional_one_of_the_students_locale(
    locale: Locale, instant: datetime, expected: date
) -> None:
    world = World(instant)
    link = world.link(zone=None, locale=locale)
    world.listed(link, {expected: P})
    student = world.detailed(link, {expected: P})

    found, _ = await world.students()
    card = await world.card(student)

    assert found[0].today is P
    assert card.days[-1].date == expected


async def test_the_teachers_zone_is_never_used() -> None:
    """Kiritimati is already on Nov 8; for the student in Honolulu it's still Nov 7."""
    world = World(datetime(2026, 11, 7, 20, tzinfo=UTC))
    student_today, teacher_today = date(2026, 11, 7), date(2026, 11, 8)
    link = world.link(zone="Pacific/Honolulu")
    shown = {student_today: P, teacher_today: R}
    world.listed(link, shown)
    student = world.detailed(link, shown)

    found, _ = await world.students()
    card = await world.card(student)

    assert found[0].today is P
    assert card.days[-1] == DayCell(student_today, P, None)


# A stored date past today waits (moving west, a period's planned end)


async def test_a_stored_date_past_today_is_not_shown_until_it_arrives(world: World) -> None:
    tomorrow = _day(1)
    link = world.link(zone="UTC")
    world.listed(link, {tomorrow: R})
    student = world.detailed(link, {tomorrow: R})

    found, _ = await world.students()
    card = await world.card(student)

    assert found[0].today is None
    assert tomorrow not in [d.date for d in card.days]
    assert all(d.shown is None for d in card.days)


async def test_no_note_while_the_link_date_is_within_21_days_of_a_western_today() -> None:
    world = World(datetime(2026, 11, 7, 9, tzinfo=UTC))
    today = date(2026, 11, 6)
    student = world.detailed(
        world.link(zone="Pacific/Honolulu", linked_on=today + timedelta(days=1))
    )

    assert (await world.card(student)).quiet is False


# What the use cases return


async def test_the_list_keeps_the_port_order_and_the_total(world: World) -> None:
    first, second = world.link("Anna"), world.link(None)
    world.listed(first, {UTC_TODAY: P})
    world.listed(second)

    found, total = await world.students()

    assert found == [
        StudentToday(first.student_id, "Anna", P),
        StudentToday(second.student_id, None, None),
    ]
    assert total == 2


async def test_an_empty_list_is_no_role_check(world: World) -> None:
    assert await world.students() == ([], 0)


async def test_the_card_carries_the_position_and_the_name(world: World) -> None:
    position = Position("intermediate", "kapotasana")
    student = world.detailed(world.link("Anna"), {UTC_TODAY: R}, position=position)

    card = await world.card(student)

    assert (card.id, card.name, card.last_asana) == (student, "Anna", position)


@pytest.mark.parametrize("position", [None, STANDING_ONLY], ids=["not-set", "standing-only"])
async def test_not_set_and_standing_only_stay_apart(
    world: World, position: Position | None
) -> None:
    student = world.detailed(world.link(), position=position)

    assert (await world.card(student)).last_asana == position


async def test_none_from_the_port_is_not_linked(world: World) -> None:
    with pytest.raises(NotLinked):
        await world.card(uuid4())


async def test_a_foreign_row_on_the_list_is_not_allowed(world: World) -> None:
    world.listed(world.link("Mine"))
    world.listed(world.link("Theirs", teacher=uuid4()))

    with pytest.raises(NotAllowed):
        await world.students()


async def test_a_foreign_row_on_the_card_is_not_allowed(world: World) -> None:
    student = world.detailed(world.link(teacher=uuid4()))

    with pytest.raises(NotAllowed):
        await world.card(student)


async def test_no_zone_link_date_or_flag_leaves_the_use_case(world: World) -> None:
    link = world.link("Anna", "Asia/Kathmandu", linked_on=date(2026, 2, 3))
    world.listed(link, {UTC_TODAY: P})
    student = world.detailed(link, {UTC_TODAY: P}, agreed=False)

    found, _ = await world.students()
    card = await world.card(student)

    for output in (repr(found), repr(card)):
        assert "Kathmandu" not in output
        assert "2026, 2, 3" not in output
        assert "agreed" not in output
        assert "locale" not in output


# The quiet note: projected dates only, and the consent flag


async def test_agreed_false_hides_the_note_and_true_shows_it(world: World) -> None:
    link = world.link(linked_on=LINKED)
    agreed = world.detailed(link)
    assert (await world.card(agreed)).quiet is True

    not_agreed = world.detailed(link, agreed=False)

    assert (await world.card(not_agreed)).quiet is False


async def test_only_the_flag_differs_between_those_two_cards(world: World) -> None:
    link = world.link()
    first = await world.card(world.detailed(link, agreed=True))
    second = await world.card(world.detailed(link, agreed=False))

    assert (first.id, first.name, first.days, first.last_asana) == (
        second.id,
        second.name,
        second.days,
        second.last_asana,
    )


async def test_a_rest_day_counts_as_a_shown_day_for_the_note(world: World) -> None:
    student = world.detailed(world.link(zone="UTC"), {_day(-20): R})

    assert (await world.card(student)).quiet is False


async def test_the_note_counts_from_the_link_date(world: World) -> None:
    recent = world.detailed(world.link(zone="UTC", linked_on=_day(-20)))
    older = world.detailed(world.link(zone="UTC", linked_on=_day(-21)))

    assert (await world.card(recent)).quiet is False
    assert (await world.card(older)).quiet is True


async def test_a_future_date_never_keeps_the_note_away(world: World) -> None:
    student = world.detailed(world.link(zone="UTC"), {_day(1): R})

    assert (await world.card(student)).quiet is True


def test_the_list_port_has_no_way_to_carry_the_flag() -> None:
    assert "quiet_note_agreed" not in SharedPage.__dataclass_fields__
    assert "quiet_note_agreed" not in SharedLog.__dataclass_fields__
    assert "quiet_note_agreed" not in StudentLink.__dataclass_fields__
    assert "quiet_note_agreed" in SharedDetail.__dataclass_fields__


# Policies: rights are one hop, and the direction matters


@dataclass
class People:
    teacher: Account
    student: Account
    third: Account
    co_student: Account
    teachers_teacher: Account
    link: StudentLink


@pytest.fixture
def people() -> People:
    accounts = InMemoryAccounts(clock=FixedClock(NOW))
    links = InMemoryTeacherLinks(accounts)
    teacher, student, third, co_student, teachers_teacher = (
        add_person(accounts, str(n)) for n in range(1, 6)
    )
    links.add(student.id, teacher.id)
    links.add(co_student.id, teacher.id)
    links.add(teacher.id, teachers_teacher.id)
    link = StudentLink(teacher.id, student.id, "Person", None, "en", LINKED)
    return People(teacher, student, third, co_student, teachers_teacher, link)


@pytest.mark.parametrize("policy", [can_view_activity, can_view_last_asana])
def test_the_links_teacher_may_view(people: People, policy: object) -> None:
    assert policy(people.teacher, people.link) is True  # type: ignore[operator]


@pytest.mark.parametrize("policy", [can_view_activity, can_view_last_asana])
@pytest.mark.parametrize("who", ["third", "co_student", "teachers_teacher", "student"])
def test_nobody_else_may_view(people: People, policy: object, who: str) -> None:
    viewer: Account = getattr(people, who)

    assert policy(viewer, people.link) is False  # type: ignore[operator]


@pytest.mark.parametrize("policy", [can_view_activity, can_view_last_asana])
def test_a_cycle_doesnt_turn_the_right_around(people: People, policy: object) -> None:
    """Peers teach each other: the reverse link is a different link, with its own teacher."""
    reversed_link = StudentLink(people.student.id, people.teacher.id, "Person", None, "en", LINKED)

    assert policy(people.teacher, reversed_link) is False  # type: ignore[operator]
    assert policy(people.student, reversed_link) is True  # type: ignore[operator]


@pytest.mark.parametrize(
    "policy", [can_view_milestones, can_view_check_ins, can_view_diary, can_view_progression]
)
def test_owner_only_policies_stay_false_for_a_linked_teacher(
    people: People, policy: object
) -> None:
    assert policy(people.teacher, people.student) is False  # type: ignore[operator]
    assert policy(people.student, people.student) is True  # type: ignore[operator]
