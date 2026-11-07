"""Teacher links, the use cases on fakes (ID-04, spec §3, §10): accepting an invite, the silent
note, caps, `linked_on` as the student's local date, rotating, re-linking, the main teacher and
the policies. A frozen clock throughout; the three `can_view_*` stay owner-only."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from tests.fakes import FakeNotifier, FixedClock, InMemoryAccounts, cities
from tests.teacher_link_fakes import FixedCodes, InMemoryTeacherLinks, add_person
from tristhana.application.policies import (
    Principal,
    can_choose_primary,
    can_manage_invite,
    can_unlink,
    can_view_check_ins,
    can_view_diary,
    can_view_progression,
)
from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus, Recipient
from tristhana.application.ports.teacher_links import Accepted, LinksChanged, NotLinked
from tristhana.application.teacher_links import (
    AcceptInvite,
    GetInvite,
    GetLinks,
    PreviewInvite,
    RemoveStudent,
    RemoveTeacher,
    RotateInvite,
    SetPrimaryTeacher,
)
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.teacher_links import (
    MAX_STUDENTS,
    MAX_TEACHERS,
    InviteState,
    effective_primary,
)

NOW = datetime(2026, 10, 18, 11, 0, tzinfo=UTC)
CODE = "aB3dE6gH9jK2mN5p"
OTHER_CODE = "Zy8xW7vU6tS5rQ4p"


@dataclass
class World:
    instant: datetime = NOW
    clock: FixedClock = field(init=False)
    accounts: InMemoryAccounts = field(init=False)
    links: InMemoryTeacherLinks = field(init=False)
    notifier: FakeNotifier = field(init=False)

    def __post_init__(self) -> None:
        self.clock = FixedClock(self.instant)
        self.accounts = InMemoryAccounts(clock=self.clock)
        self.links = InMemoryTeacherLinks(self.accounts)
        self.notifier = FakeNotifier()

    def person(
        self,
        telegram_id: str,
        name: str | None = "Person",
        locale: Locale = "en",
        zone: str | None = "Asia/Almaty",
    ) -> Account:
        return add_person(self.accounts, telegram_id, name, locale, zone)

    def teacher(self, telegram_id: str = "1", code: str = CODE, locale: Locale = "ru") -> Account:
        account = self.person(telegram_id, "Лена", locale)
        self.links.codes[account.id] = code
        return account

    async def accept(self, student: Account, code: str = CODE) -> Accepted | None:
        use_case = AcceptInvite(self.links, self.notifier, self.clock, cities())
        return await use_case.execute(Principal(student), code)

    async def accepted(self, student: Account, code: str = CODE) -> Accepted:
        result = await self.accept(student, code)
        assert result is not None
        return result


@pytest.fixture
def world() -> World:
    return World()


# Accepting


async def test_accept_links_and_tells_the_teacher_once_in_their_language(world: World) -> None:
    teacher = world.teacher(telegram_id="1001", locale="ru")
    student = world.person("2", "Ash", "en")

    accepted = await world.accepted(student)

    assert accepted.created is True
    assert accepted.teacher_id == teacher.id
    assert world.links.teachers_of(student.id) == [teacher.id]
    assert world.notifier.joined == [(Recipient("1001", "ru"), "Ash")]


async def test_a_double_tap_tells_the_teacher_once(world: World) -> None:
    teacher = world.teacher()
    student = world.person("2")

    first = await world.accepted(student)
    second = await world.accepted(student)

    assert first.created is True
    assert second.created is False
    assert second.already is True
    assert world.links.teachers_of(student.id) == [teacher.id]
    assert len(world.notifier.joined) == 1


@pytest.mark.parametrize(
    "status", [DeliveryStatus.BLOCKED, DeliveryStatus.FAILED, DeliveryStatus.RETRY_AFTER]
)
async def test_an_undelivered_note_never_reaches_the_student(
    world: World, status: DeliveryStatus
) -> None:
    """No retry: the list is the record. No mark either: `AcceptInvite` isn't handed the
    notification repository, because `mark_unreachable` belongs to the tick."""
    teacher = world.teacher()
    student = world.person("2")
    world.notifier.join_outcomes.append(DeliveryResult(status))

    accepted = await world.accepted(student)

    assert accepted.created is True
    assert world.links.teachers_of(student.id) == [teacher.id]
    assert len(world.notifier.joined) == 1


async def test_an_unknown_code_is_none_and_silent(world: World) -> None:
    student = world.person("2")

    assert await world.accept(student, "unknownCode00000") is None
    assert world.notifier.joined == []


async def test_ones_own_code_links_nothing(world: World) -> None:
    teacher = world.teacher()

    accepted = await world.accepted(teacher)

    assert accepted.created is False
    assert accepted.teacher_id == teacher.id
    assert world.links.rows == {}
    assert world.notifier.joined == []


async def test_the_students_cap_refuses_the_next_teacher(world: World) -> None:
    teacher = world.teacher()
    student = world.person("2")
    for _ in range(MAX_TEACHERS):
        world.links.add(student.id, uuid4())

    accepted = await world.accepted(student)

    assert accepted.created is False
    assert teacher.id not in world.links.teachers_of(student.id)
    assert world.notifier.joined == []


async def test_the_teachers_cap_refuses_the_next_student(world: World) -> None:
    teacher = world.teacher()
    student = world.person("2")
    for _ in range(MAX_STUDENTS):
        world.links.add(uuid4(), teacher.id)

    accepted = await world.accepted(student)

    assert accepted.created is False
    assert student.id not in world.links.students_of(teacher.id)
    assert world.notifier.joined == []


async def test_one_place_below_the_caps_is_enough(world: World) -> None:
    teacher = world.teacher()
    student = world.person("2")
    for _ in range(MAX_TEACHERS - 1):
        world.links.add(student.id, uuid4())
    for _ in range(MAX_STUDENTS - 1):
        world.links.add(uuid4(), teacher.id)

    accepted = await world.accepted(student)

    assert accepted.created is True


@pytest.mark.parametrize(
    ("zone", "instant", "expected"),
    [
        # One instant, two calendar days: the far ends of the map.
        ("Pacific/Kiritimati", NOW, date(2026, 10, 19)),  # +14: 01:00 tomorrow
        ("Pacific/Honolulu", NOW, date(2026, 10, 18)),  # -10: 01:00 today
        # The minute of local midnight in the zones with odd offsets and DST.
        ("Asia/Kolkata", datetime(2026, 10, 18, 18, 29, tzinfo=UTC), date(2026, 10, 18)),
        ("Asia/Kolkata", datetime(2026, 10, 18, 18, 30, tzinfo=UTC), date(2026, 10, 19)),
        ("Asia/Kathmandu", datetime(2026, 10, 18, 18, 14, tzinfo=UTC), date(2026, 10, 18)),
        ("Asia/Kathmandu", datetime(2026, 10, 18, 18, 15, tzinfo=UTC), date(2026, 10, 19)),
        ("Europe/Berlin", datetime(2026, 7, 1, 22, 0, tzinfo=UTC), date(2026, 7, 2)),  # CEST
        ("Europe/Berlin", datetime(2026, 12, 1, 22, 0, tzinfo=UTC), date(2026, 12, 1)),  # CET
        ("Asia/Almaty", datetime(2026, 10, 18, 19, 0, tzinfo=UTC), date(2026, 10, 19)),
        ("Europe/Moscow", datetime(2026, 10, 18, 21, 0, tzinfo=UTC), date(2026, 10, 19)),
        ("America/New_York", datetime(2026, 10, 19, 3, 59, tzinfo=UTC), date(2026, 10, 18)),
    ],
)
async def test_linked_on_is_the_students_local_date(
    zone: str, instant: datetime, expected: date
) -> None:
    world = World(instant)
    teacher = world.teacher()  # in Asia/Almaty: their date must play no part
    student = world.person("2", zone=zone)

    await world.accept(student)

    assert world.links.rows[(student.id, teacher.id)].linked_on == expected


@pytest.mark.parametrize(
    ("locale", "expected"),
    [("en", date(2026, 10, 18)), ("ru", date(2026, 10, 19))],  # provisional: UTC, Moscow
)
async def test_linked_on_uses_the_provisional_zone_when_none_is_known(
    locale: Locale, expected: date
) -> None:
    world = World(datetime(2026, 10, 18, 22, 0, tzinfo=UTC))
    teacher = world.teacher()
    student = world.person("2", locale=locale, zone=None)

    await world.accept(student)

    assert world.links.rows[(student.id, teacher.id)].linked_on == expected


async def test_rotating_kills_the_old_code_and_keeps_the_links(world: World) -> None:
    teacher = world.teacher()
    student, latecomer = world.person("2"), world.person("3")
    await world.accept(student)

    fresh = await RotateInvite(world.links, FixedCodes(OTHER_CODE)).execute(Principal(teacher))

    assert fresh == OTHER_CODE
    assert await world.accept(latecomer, CODE) is None
    assert world.links.teachers_of(student.id) == [teacher.id]
    accepted = await world.accepted(latecomer, OTHER_CODE)
    assert accepted.created is True


async def test_a_relink_is_a_fresh_row_with_a_new_linked_on(world: World) -> None:
    teacher = world.teacher()
    student = world.person("2", zone="UTC")
    await world.accept(student)
    first = world.links.rows[(student.id, teacher.id)]
    await SetPrimaryTeacher(world.links, cities()).execute(Principal(student), teacher.id)
    await RemoveTeacher(world.links, cities()).execute(Principal(student), teacher.id)

    world.clock.instant = NOW + timedelta(days=3)
    await world.accept(student)

    again = world.links.rows[(student.id, teacher.id)]
    assert again.linked_on == date(2026, 10, 21)
    assert again.created_at > first.created_at
    assert again.is_primary is False  # nothing comes back from the old link
    assert len(world.notifier.joined) == 2  # a new link is a new student on the list


async def test_accepted_flags_a_second_link_and_not_a_first(world: World) -> None:
    world.teacher("1", CODE)
    world.teacher("3", OTHER_CODE)
    student = world.person("2")

    first = await world.accepted(student, CODE)
    second = await world.accepted(student, OTHER_CODE)

    assert first.my_teachers == 1
    assert second.my_teachers == 2


async def test_no_error_carries_the_code(world: World) -> None:
    world.teacher()
    student = world.person("2")
    world.links.fail_with = RuntimeError("storage fell over")

    with pytest.raises(RuntimeError) as caught:
        await world.accept(student)

    assert CODE not in f"{caught.value!s} {caught.value!r}"
    assert NotLinked().args == ()
    assert LinksChanged().args == ()


# Previews


@pytest.mark.parametrize(
    ("own", "already", "expected"),
    [
        (False, False, InviteState.OPEN),
        (True, False, InviteState.OWN),
        (False, True, InviteState.ALREADY),
    ],
)
async def test_preview_states(
    world: World, own: bool, already: bool, expected: InviteState
) -> None:
    teacher = world.teacher()
    student = teacher if own else world.person("2")
    if already:
        world.links.add(student.id, teacher.id)

    preview = await PreviewInvite(world.links).execute(Principal(student), CODE)

    assert preview is not None
    assert preview.state is expected
    assert preview.name == "Лена"


async def test_preview_says_full_on_either_cap(world: World) -> None:
    teacher = world.teacher()
    student = world.person("2")
    for _ in range(MAX_STUDENTS):
        world.links.add(uuid4(), teacher.id)

    preview = await PreviewInvite(world.links).execute(Principal(student), CODE)

    assert preview is not None
    assert preview.state is InviteState.FULL


async def test_preview_of_an_unknown_code_is_none_and_writes_nothing(world: World) -> None:
    student = world.person("2")

    assert await PreviewInvite(world.links).execute(Principal(student), CODE) is None
    assert world.links.rows == {}


# The invite, the lists, the main teacher, removal


async def test_get_invite_makes_one_code_and_keeps_it(world: World) -> None:
    me = world.person("1")
    codes = FixedCodes(CODE, OTHER_CODE)

    first = await GetInvite(world.links, codes).execute(Principal(me))
    second = await GetInvite(world.links, codes).execute(Principal(me))

    assert (first, second) == (CODE, CODE)


async def test_lists_show_both_sides_with_names_and_nothing_of_the_main_teacher(
    world: World,
) -> None:
    teacher, student = world.person("1", "Лена"), world.person("2", "Ash")
    world.links.add(student.id, teacher.id, primary=True)

    as_student = await GetLinks(world.links).execute(Principal(student))
    as_teacher = await GetLinks(world.links).execute(Principal(teacher))

    assert [(t.id, t.name, t.chosen_primary) for t in as_student.teachers] == [
        (teacher.id, "Лена", True)
    ]
    assert as_student.students == ()
    assert [(s.id, s.name, s.chosen_primary) for s in as_teacher.students] == [
        (student.id, "Ash", False)  # chosen, and still not told
    ]


async def test_a_student_picks_their_main_teacher(world: World) -> None:
    first, second, student = world.person("1"), world.person("3"), world.person("2")
    world.links.add(student.id, first.id)
    world.links.add(student.id, second.id)

    await SetPrimaryTeacher(world.links, cities()).execute(Principal(student), second.id)

    links = await GetLinks(world.links).execute(Principal(student))
    assert effective_primary(links.teachers) == second.id


async def test_a_main_teacher_must_be_on_the_list(world: World) -> None:
    student, stranger = world.person("2"), world.person("9")

    with pytest.raises(NotLinked):
        await SetPrimaryTeacher(world.links, cities()).execute(Principal(student), stranger.id)


async def test_losing_the_race_for_main_says_links_changed(world: World) -> None:
    teacher, student = world.person("1"), world.person("2")
    world.links.add(student.id, teacher.id)
    world.links.lose_next_flip = True

    with pytest.raises(LinksChanged):
        await SetPrimaryTeacher(world.links, cities()).execute(Principal(student), teacher.id)


async def test_either_side_removes_and_removing_twice_is_fine(world: World) -> None:
    teacher, student, other = world.person("1"), world.person("2"), world.person("3")
    world.links.add(student.id, teacher.id)
    world.links.add(other.id, teacher.id)

    await RemoveTeacher(world.links, cities()).execute(Principal(student), teacher.id)
    await RemoveTeacher(world.links, cities()).execute(Principal(student), teacher.id)
    await RemoveStudent(world.links).execute(Principal(teacher), other.id)
    await RemoveStudent(world.links).execute(Principal(teacher), other.id)

    assert world.links.rows == {}
    assert world.notifier.joined == []  # removal is silent both ways


async def test_a_removal_is_keyed_on_the_caller(world: World) -> None:
    teacher, student, stranger = world.person("1"), world.person("2"), world.person("3")
    world.links.add(student.id, teacher.id)

    await RemoveTeacher(world.links, cities()).execute(Principal(stranger), teacher.id)
    await RemoveStudent(world.links).execute(Principal(stranger), student.id)

    assert world.links.teachers_of(student.id) == [teacher.id]


# Policies


def test_can_unlink_is_for_either_side_and_no_third_person(world: World) -> None:
    teacher, student, third = world.person("1"), world.person("2"), world.person("3")

    assert can_unlink(student, student.id, teacher.id) is True
    assert can_unlink(teacher, student.id, teacher.id) is True
    assert can_unlink(third, student.id, teacher.id) is False


def test_can_choose_primary_is_for_the_student_only(world: World) -> None:
    teacher, student = world.person("1"), world.person("2")

    assert can_choose_primary(student, student.id) is True
    assert can_choose_primary(teacher, student.id) is False


def test_can_manage_invite_is_for_the_owner_only(world: World) -> None:
    owner, other = world.person("1"), world.person("2")

    assert can_manage_invite(owner, owner) is True
    assert can_manage_invite(other, owner) is False


@pytest.mark.parametrize("policy", [can_view_check_ins, can_view_diary, can_view_progression])
def test_a_linked_teacher_still_sees_nothing_until_st06(world: World, policy: object) -> None:
    teacher, student = world.person("1"), world.person("2")
    world.links.add(student.id, teacher.id, primary=True)

    assert policy(teacher, student) is False  # type: ignore[operator]
    assert policy(student, teacher) is False  # type: ignore[operator]  # nor the other way
    assert policy(student, student) is True  # type: ignore[operator]
