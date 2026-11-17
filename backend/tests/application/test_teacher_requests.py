"""Teacher requests, the use cases on fakes (ID-07 spec §3, §8; ADR-0046): the ask with the
student's local date and the one silent note, the refusals, the approval that makes the link,
decline and Undo, Confirm all, withdrawing, validity as a read-time join, the closing notes'
read, and the policies as a role by action matrix.

Two things are pinned throughout: a waiting or declined request grants nothing a link grants,
and nothing the student can read back tells a quiet "no" from waiting."""

import asyncio
import inspect
import itertools
from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from tests.fakes import FakeNotifier, FixedClock, InMemoryAccounts, InMemoryStorage, cities
from tests.moon_follow_fakes import FollowingAccounts
from tests.shala_fakes import InMemoryShalas, shala_storage
from tests.teacher_link_fakes import InMemoryTeacherLinks, add_person
from tests.teacher_request_fakes import InMemoryTeacherRequests
from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_answer_request,
    can_ask_teacher,
    can_withdraw_request,
)
from tristhana.application.ports.notifications import (
    DeliveryResult,
    DeliveryStatus,
    Recipient,
    TeacherAsked,
)
from tristhana.application.ports.teacher_links import NotLinked
from tristhana.application.ports.teacher_requests import (
    Answer,
    Answered,
    ApprovedAll,
    AskedTeacher,
    CardRequests,
    Choices,
    TeacherChoice,
    Withdrawn,
)
from tristhana.application.teacher_links import GetLinks, RemoveStudent, RemoveTeacher
from tristhana.application.teacher_requests import (
    ApproveAllRequests,
    ApproveRequest,
    AskResult,
    AskTeacher,
    DeclineRequest,
    GetCardRequests,
    GetMyRequests,
    GetTeacherChoices,
    GetWaitingRequests,
    ReopenRequest,
    WithdrawRequest,
)
from tristhana.application.teacher_view import GetStudent, GetStudents
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.progression import Track
from tristhana.domain.shalas import Membership, ShalaRole
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS
from tristhana.domain.teacher_requests import (
    ANSWER_WITHIN,
    KEEP,
    MAX_ASKING,
    AskState,
    Closing,
    RequestCaps,
    RequestConsent,
    RequestState,
    grants_quiet_note,
)

NOW = datetime(2026, 11, 17, 10, 30, tzinfo=UTC)
# The fake's rows are a few microseconds apart, as rows are in a database; the exact
# boundaries are the domain tests'.
A_MOMENT = timedelta(seconds=1)
TEACHER, ASSISTANT, OFFICE, ADMIN = (
    ShalaRole.TEACHER,
    ShalaRole.ASSISTANT,
    ShalaRole.OFFICE,
    ShalaRole.ADMIN,
)
_ids = itertools.count(1000)


@dataclass
class World:
    storage: InMemoryStorage = field(default_factory=shala_storage)
    notifier: FakeNotifier = field(default_factory=FakeNotifier)
    clock: FixedClock = field(init=False)
    links: InMemoryTeacherLinks = field(init=False)
    shalas: InMemoryShalas = field(init=False)
    requests: InMemoryTeacherRequests = field(init=False)
    owner: Account = field(init=False)
    shala: UUID = field(init=False)

    def __post_init__(self) -> None:
        self.clock = self.storage.repo.clock
        self.clock.instant = NOW
        self.links = self.storage.teacher_links
        self.shalas = self.storage.shalas
        self.requests = self.storage.teacher_requests
        self.owner = self.person("Olga")
        self.shala = self.shalas.add_shala(self.owner.id, roles=frozenset()).id

    def person(
        self, name: str | None = "Person", locale: Locale = "en", zone: str | None = "Asia/Almaty"
    ) -> Account:
        return add_person(self.storage.repo, str(next(_ids)), name, locale, zone)

    def teacher(
        self, name: str = "Anna", locale: Locale = "ru", shala: UUID | None = None
    ) -> Account:
        account = self.person(name, locale)
        self.shalas.add_staff(shala or self.shala, account.id, TEACHER)
        return account

    def student(
        self,
        name: str | None = "Ash",
        locale: Locale = "en",
        zone: str | None = "Asia/Almaty",
        shala: UUID | None = None,
    ) -> Account:
        account = self.person(name, locale, zone)
        self.shalas.add_student(shala or self.shala, account.id)
        return account

    def later(self, delta: timedelta) -> None:
        self.clock.instant += delta

    # The use cases, as the composition root builds them.

    async def choices(self, who: Account, shala: UUID | None = None):
        use_case = GetTeacherChoices(self.requests, self.clock)
        return await use_case.execute(Principal(who), shala or self.shala)

    async def card(self, who: Account, shala: UUID | None = None) -> CardRequests:
        use_case = GetCardRequests(self.requests, self.clock)
        return await use_case.execute(Principal(who), shala or self.shala)

    async def ask(
        self,
        student: Account,
        teacher: Account,
        shala: UUID | None = None,
        consent: RequestConsent = RequestConsent.FIRST,
    ) -> AskResult:
        use_case = AskTeacher(self.requests, self.notifier, self.clock)
        return await use_case.execute(
            Principal(student), shala or self.shala, teacher.id, consent=consent
        )

    def without_the_note(self, student: Account, teacher: Account) -> None:
        """A request whose consent granted no quiet note. No `RequestConsent` grants that
        today (ADR-0049), but a row says only what its consent granted, and the approval
        copies whatever the row holds."""
        self.requests.rows[(student.id, teacher.id)].quiet_note_agreed = False

    async def withdraw(self, student: Account, teacher: Account) -> Withdrawn:
        return await WithdrawRequest(self.requests).execute(Principal(student), teacher.id)

    async def mine(self, who: Account):
        return await GetMyRequests(self.requests, self.clock).execute(Principal(who))

    async def waiting(
        self,
        teacher: Account,
        offset: int = 0,
        limit: int = 10,
        student: UUID | None = None,
        before: datetime | None = None,
    ):
        use_case = GetWaitingRequests(self.requests, self.clock)
        return await use_case.execute(Principal(teacher), offset, limit, student, before)

    async def approve(self, teacher: Account, student: Account) -> Answer:
        use_case = ApproveRequest(self.requests, self.clock)
        return await use_case.execute(Principal(teacher), student.id)

    async def approve_all(self, teacher: Account, before: datetime) -> ApprovedAll:
        use_case = ApproveAllRequests(self.requests, self.clock)
        return await use_case.execute(Principal(teacher), before)

    async def decline(self, teacher: Account, student: Account) -> Answer:
        use_case = DeclineRequest(self.requests, self.clock)
        return await use_case.execute(Principal(teacher), student.id)

    async def reopen(self, teacher: Account, student: Account) -> Answer:
        use_case = ReopenRequest(self.requests, self.clock)
        return await use_case.execute(Principal(teacher), student.id)

    def state(self, student: Account, teacher: Account) -> RequestState | None:
        return self.requests.state_of(student.id, teacher.id)


@pytest.fixture
def world() -> World:
    return World()


# The question: who can be asked


async def test_only_the_teacher_role_is_offered(world: World) -> None:
    anna, boris = world.teacher("Anna"), world.teacher("Boris")
    for role in (ASSISTANT, OFFICE, ADMIN):
        world.shalas.add_staff(world.shala, world.person(role.value).id, role)
    student = world.student()

    found = await world.choices(student)

    assert found.offer == (TeacherChoice(anna.id, "Anna"), TeacherChoice(boris.id, "Boris"))
    assert found.waiting == ()
    assert (found.shala_id, found.shala_name) == (world.shala, "Ashtanga Almaty")


async def test_an_owner_is_offered_only_with_the_teacher_role(world: World) -> None:
    student = world.student()
    assert (await world.choices(student)).offer == ()  # the owner holds no role here

    world.shalas.staff[(world.shala, world.owner.id)].roles = frozenset({TEACHER, ADMIN})

    assert (await world.choices(student)).offer == (TeacherChoice(world.owner.id, "Olga"),)


async def test_linked_and_already_asked_teachers_are_not_offered(world: World) -> None:
    linked, asked, free = world.teacher("Linked"), world.teacher("Asked"), world.teacher("Free")
    student = world.student()
    world.links.add(student.id, linked.id)
    await world.ask(student, asked)

    found = await world.choices(student)

    assert found.offer == (TeacherChoice(free.id, "Free"),)
    assert found.waiting == (TeacherChoice(asked.id, "Asked"),)


async def test_a_teacher_is_offered_again_after_thirty_days(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.withdraw(student, teacher)

    world.later(KEEP - timedelta(minutes=1))
    assert (await world.choices(student)).offer == ()
    world.later(timedelta(minutes=2))  # the row is still there: the rule is not the prune's

    assert (await world.choices(student)).offer == (TeacherChoice(teacher.id, "Anna"),)


async def test_the_question_is_for_students_of_the_shala_only(world: World) -> None:
    teacher = world.teacher()

    for who in (world.person("Stranger"), teacher, world.owner):
        with pytest.raises(NotFound):
            await world.choices(who)
    with pytest.raises(NotFound):
        await world.choices(world.student(), uuid4())


# The requests part of a shala card: one read for either side


async def test_the_card_read_gives_a_student_their_choices_and_a_teacher_the_count(
    world: World,
) -> None:
    anna, boris = world.teacher("Anna"), world.teacher("Boris")
    student, other = world.student(), world.student("Bea")
    await world.ask(student, anna)
    await world.ask(other, anna)
    world.requests.calls.clear()

    mine, theirs = await world.card(student), await world.card(anna)

    assert mine == CardRequests(await world.choices(student), 0)
    assert mine.asked == Choices(
        world.shala,
        "Ashtanga Almaty",
        (TeacherChoice(boris.id, "Boris"),),
        (TeacherChoice(anna.id, "Anna"),),
    )
    assert theirs == CardRequests(None, 2)
    assert world.requests.calls[:2] == ["card", "card"]  # one call each, no second read


async def test_the_card_read_counts_only_for_a_teacher_of_that_shala(world: World) -> None:
    """The count is for every shala I teach in, and shown on the cards of those alone:
    not to the owner or a manager (Q322), and not where I am front desk or a student."""
    anna, student = world.teacher("Anna"), world.student()
    await world.ask(student, anna)
    elsewhere = world.shalas.add_shala(world.owner.id, "Ashtanga Astana", roles=frozenset()).id
    world.shalas.add_staff(elsewhere, anna.id, OFFICE)
    third = world.shalas.add_shala(world.owner.id, "Ashtanga Aktau", roles=frozenset()).id
    world.shalas.add_staff(third, anna.id, TEACHER)
    manager = world.person("Mara")
    world.shalas.add_staff(world.shala, manager.id, ADMIN)

    assert await world.card(anna, third) == CardRequests(None, 1)  # asked in another shala
    assert await world.card(anna, elsewhere) == CardRequests(None, 0)
    for who in (world.owner, manager, world.person("Stranger")):
        assert await world.card(who) == CardRequests(None, 0)
    assert await world.card(student, uuid4()) == CardRequests(None, 0)


# The ask


@pytest.mark.parametrize(
    ("zone", "locale", "asked_on"),
    [
        ("Pacific/Kiritimati", "en", date(2026, 11, 18)),  # 00:30 the next day
        ("Pacific/Honolulu", "en", date(2026, 11, 17)),  # 00:30 the same day
        (None, "ru", date(2026, 11, 17)),  # provisional: Moscow, 13:30
        (None, "en", date(2026, 11, 17)),  # provisional: UTC
    ],
)
async def test_ask_stores_the_students_local_date(
    world: World, zone: str | None, locale: Locale, asked_on: date
) -> None:
    teacher = world.teacher()
    student = world.student(zone=zone, locale=locale)

    result = await world.ask(student, teacher)

    assert result == AskResult(AskState.CREATED, "Anna")
    row = world.requests.rows[(student.id, teacher.id)]
    assert (row.asked_on, row.state, row.shala_id) == (asked_on, RequestState.WAITING, world.shala)


async def test_ask_tells_the_teacher_once_in_their_language(world: World) -> None:
    teacher = world.teacher(locale="ru")
    student = world.student("Ash")
    telegram_id = world.requests._telegram_id(teacher.id)  # pyright: ignore[reportPrivateUsage]
    assert telegram_id is not None

    await world.ask(student, teacher)

    assert world.notifier.asked == [
        (Recipient(telegram_id, "ru"), TeacherAsked(student.id, "Ash", "Ashtanga Almaty", 1))
    ]
    assert world.notifier.joined == []  # nothing is a link yet


async def test_the_note_counts_who_is_waiting(world: World) -> None:
    teacher = world.teacher()
    for name in ("Ash", "Bea", "Cy"):
        await world.ask(world.student(name), teacher)

    assert [asked.waiting for _, asked in world.notifier.asked] == [1, 2, 3]


async def test_a_double_tap_asks_and_notifies_once(world: World) -> None:
    teacher, student = world.teacher(), world.student()

    first, second = await asyncio.gather(world.ask(student, teacher), world.ask(student, teacher))

    assert sorted([first.state, second.state]) == [AskState.CREATED, AskState.WAITING]
    assert len(world.notifier.asked) == 1
    assert world.requests.writes == ["ask"]


@pytest.mark.parametrize("status", [DeliveryStatus.FAILED, DeliveryStatus.BLOCKED])
async def test_a_failed_note_still_asks(world: World, status: DeliveryStatus) -> None:
    teacher, student = world.teacher(), world.student()
    world.notifier.ask_outcomes.append(DeliveryResult(status))

    result = await world.ask(student, teacher)

    assert result.state is AskState.CREATED
    assert world.state(student, teacher) is RequestState.WAITING
    assert (await world.waiting(teacher)).total == 1  # the list is the record


async def test_a_teacher_without_telegram_gets_no_note(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    world.storage.repo.identities.clear()

    assert (await world.ask(student, teacher)).state is AskState.CREATED
    assert world.notifier.asked == []


@pytest.mark.parametrize("consent", list(RequestConsent))
async def test_the_request_stores_what_its_named_consent_grants(
    world: World, consent: RequestConsent
) -> None:
    """ADR-0049: the client names the consent it showed; the domain says what it grants."""
    anna, student = world.teacher("Anna"), world.student()

    await world.ask(student, anna, consent=consent)

    stored = world.requests.rows[(student.id, anna.id)].quiet_note_agreed
    assert stored is grants_quiet_note(consent)


async def test_the_first_request_consent_stores_the_quiet_note(world: World) -> None:
    anna, student = world.teacher("Anna"), world.student()

    await world.ask(student, anna, consent=RequestConsent.FIRST)

    assert world.requests.rows[(student.id, anna.id)].quiet_note_agreed is True


def test_ask_takes_a_named_consent_and_no_flag() -> None:
    parameters = inspect.signature(AskTeacher.execute).parameters

    assert "quiet_note_agreed" not in parameters
    assert parameters["consent"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["consent"].annotation in (RequestConsent, "RequestConsent")


async def test_what_the_student_gets_back_holds_no_teacher_side_fact(world: World) -> None:
    assert {f.name for f in fields(AskResult)} == {"state", "teacher_name"}
    assert {f.name for f in fields(AskedTeacher)} == {
        "teacher_id",
        "name",
        "shala_id",
        "shala_name",
    }
    assert {f.name for f in fields(TeacherChoice)} == {"id", "name"}


# Refusals


async def test_asking_a_linked_teacher_says_linked(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    world.links.add(student.id, teacher.id)

    assert (await world.ask(student, teacher)).state is AskState.LINKED
    assert world.requests.rows == {}
    assert world.notifier.asked == []


async def test_asking_twice_says_waiting_then_recent(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)

    assert (await world.ask(student, teacher)).state is AskState.WAITING
    world.later(ANSWER_WITHIN + A_MOMENT)
    assert (await world.ask(student, teacher)).state is AskState.RECENT
    world.later(KEEP - ANSWER_WITHIN)
    assert (await world.ask(student, teacher)).state is AskState.CREATED  # a month on

    assert len(world.notifier.asked) == 2  # one message a month at most


async def test_a_new_ask_after_a_month_is_a_new_request(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    old = world.requests.rows[(student.id, teacher.id)].id
    await world.decline(teacher, student)
    world.later(KEEP + A_MOMENT)

    await world.ask(student, teacher)

    row = world.requests.rows[(student.id, teacher.id)]
    assert row.state is RequestState.WAITING
    assert row.id != old  # the ledger key of the first note can't swallow the second
    assert row.asked_on == date(2026, 12, 17)


async def test_three_asks_in_seven_days_are_the_most_and_a_withdrawal_frees_none(
    world: World,
) -> None:
    """Or "ask three, withdraw three, ask three more" would reach every teacher of a shala
    with a message each. The slot comes back seven days after the ask that took it."""
    student = world.student()
    first, second, third, fourth, fifth = (world.teacher(f"T{n}") for n in range(5))
    assert (await world.ask(student, first)).state is AskState.CREATED
    world.later(timedelta(days=1))
    for teacher in (second, third):
        assert (await world.ask(student, teacher)).state is AskState.CREATED
    assert (await world.ask(student, fourth)).state is AskState.TOO_MANY

    await world.withdraw(student, second)

    assert (await world.mine(student)).asked == (
        AskedTeacher(first.id, "T0", world.shala, "Ashtanga Almaty"),
        AskedTeacher(third.id, "T2", world.shala, "Ashtanga Almaty"),
    )  # two wait, and the third slot is still taken
    assert (await world.ask(student, fourth)).state is AskState.TOO_MANY
    world.later(ANSWER_WITHIN - timedelta(days=1) - A_MOMENT)  # just short of a week
    assert (await world.ask(student, fourth)).state is AskState.TOO_MANY
    world.later(2 * A_MOMENT)  # seven days after the first ask
    assert (await world.ask(student, fourth)).state is AskState.CREATED
    assert (await world.ask(student, fifth)).state is AskState.TOO_MANY  # three again
    assert len(world.notifier.asked) == 4


async def test_withdrawing_all_three_frees_no_slot(world: World) -> None:
    student = world.student()
    teachers = [world.teacher(f"T{n}") for n in range(2 * MAX_ASKING)]
    for teacher in teachers[:MAX_ASKING]:
        await world.ask(student, teacher)
        await world.withdraw(student, teacher)

    for teacher in teachers[MAX_ASKING:]:
        assert (await world.ask(student, teacher)).state is AskState.TOO_MANY
    assert len(world.notifier.asked) == MAX_ASKING


async def test_a_confirmed_ask_is_a_link_and_takes_no_asking_slot(world: World) -> None:
    student = world.student()
    teachers = [world.teacher(f"T{n}") for n in range(MAX_ASKING + 2)]
    for teacher in teachers[:MAX_ASKING]:
        await world.ask(student, teacher)

    await world.approve(teachers[0], student)

    assert (await world.ask(student, teachers[-2])).state is AskState.CREATED
    assert (await world.ask(student, teachers[-1])).state is AskState.TOO_MANY


async def test_a_quiet_no_frees_no_slot(world: World) -> None:
    student = world.student()
    teachers = [world.teacher(f"T{n}") for n in range(MAX_ASKING + 1)]
    for teacher in teachers[:MAX_ASKING]:
        await world.ask(student, teacher)

    await world.decline(teachers[0], student)

    assert (await world.ask(student, teachers[-1])).state is AskState.TOO_MANY


async def test_a_full_teacher_says_only_not_right_now(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    for _ in range(3):
        world.requests.add(world.student().id, teacher.id, world.shala)
    guarded = await world.requests.ask(
        world.shala, student.id, teacher.id, date(2026, 11, 17), True, RequestCaps(waiting=3), NOW
    )

    assert guarded.value is not None
    assert guarded.value.state is AskState.FULL
    assert world.state(student, teacher) is None
    assert world.notifier.asked == []


async def test_asking_needs_a_student_and_a_teacher(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    assistant = world.person("Assistant")
    world.shalas.add_staff(world.shala, assistant.id, ASSISTANT)

    with pytest.raises(NotFound):  # not a member: the shala can't be probed
        await world.ask(world.person("Stranger"), teacher)
    with pytest.raises(NotAllowed):  # staff don't ask
        await world.ask(assistant, teacher)
    with pytest.raises(NotAllowed):  # an assistant can't be asked
        await world.ask(student, assistant)
    with pytest.raises(NotAllowed):  # nor the owner without the Teacher role
        await world.ask(student, world.owner)
    with pytest.raises(NotAllowed):  # nor another student, nor a stranger
        await world.ask(student, world.student("Bea"))
    assert world.requests.rows == {}
    assert world.notifier.asked == []


# The approval


@pytest.mark.parametrize("agreed", [True, False])
async def test_approve_makes_the_link_from_the_day_the_student_asked(
    world: World, agreed: bool
) -> None:
    teacher = world.teacher()
    student = world.student(zone="Pacific/Kiritimati")
    await world.ask(student, teacher)
    if not agreed:
        world.without_the_note(student, teacher)
    world.later(timedelta(days=3))

    answer = await world.approve(teacher, student)

    assert answer == Answer(Answered.DONE, "Ash", 0)
    link = world.links.rows[(student.id, teacher.id)]
    assert link.linked_on == date(2026, 11, 18)  # the ask, in the student's zone
    assert link.quiet_note_agreed is agreed  # copied, never set
    assert link.is_primary is False
    assert link.created_at >= NOW + timedelta(days=3)  # the approval's instant
    assert world.state(student, teacher) is RequestState.APPROVED


async def test_approve_sends_nothing(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    sent = len(world.notifier.asked)

    await world.approve(teacher, student)

    assert len(world.notifier.asked) == sent
    assert world.notifier.joined == []  # the student's note is the tick's
    assert world.notifier.delivered == []


async def test_two_taps_make_one_link(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)

    first, second = await asyncio.gather(
        world.approve(teacher, student), world.approve(teacher, student)
    )

    assert sorted([first.outcome, second.outcome]) == [Answered.ALREADY, Answered.DONE]
    assert world.links.students_of(teacher.id) == [student.id]


async def test_a_yes_on_someone_already_linked_says_so(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    world.links.add(student.id, teacher.id, linked_on=date(2026, 11, 20))  # the personal link

    assert (await world.approve(teacher, student)).outcome is Answered.ALREADY
    assert (await world.decline(teacher, student)).outcome is Answered.ALREADY

    assert world.links.rows[(student.id, teacher.id)].linked_on == date(2026, 11, 20)
    assert (student.id, teacher.id) in world.links.rows  # a "no" never removes a link


async def test_a_yes_after_seven_days_is_gone(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    world.later(ANSWER_WITHIN + A_MOMENT)

    assert await world.approve(teacher, student) == Answer(Answered.GONE)
    assert world.links.rows == {}


async def test_gone_is_one_answer_for_every_reason(world: World) -> None:
    teacher = world.teacher()
    expired, withdrawn, left, never = (world.student(n) for n in ("E", "W", "L", "N"))
    for student in (expired, withdrawn, left):
        world.requests.add(student.id, teacher.id, world.shala)
    world.requests.rows[(expired.id, teacher.id)].created_at -= ANSWER_WITHIN
    await world.withdraw(withdrawn, teacher)
    del world.shalas.students_rows[(world.shala, left.id)]

    answers = [await world.approve(teacher, s) for s in (expired, withdrawn, left, never)]
    answers += [await world.decline(teacher, s) for s in (expired, withdrawn, left, never)]
    answers += [await world.reopen(teacher, s) for s in (expired, withdrawn, left, never)]

    assert set(answers) == {Answer(Answered.GONE)}
    assert world.links.rows == {}


async def test_a_full_list_keeps_the_request_waiting(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    for _ in range(2):
        world.links.add(world.person().id, teacher.id)

    answer = await world.requests.approve(teacher.id, student.id, RequestCaps(students=2), NOW)

    assert answer.outcome is Answered.FULL
    assert world.state(student, teacher) is RequestState.WAITING
    assert (await world.waiting(teacher)).total == 1


async def test_the_real_caps_are_the_link_caps(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    for _ in range(MAX_TEACHERS):
        world.links.add(student.id, world.person().id)

    assert (await world.approve(teacher, student)).outcome is Answered.FULL
    assert MAX_STUDENTS == 500


# Decline and Undo


async def test_decline_then_yes_works_inside_the_window_and_not_after(world: World) -> None:
    teacher, early, late = world.teacher(), world.student("Early"), world.student("Late")
    await world.ask(early, teacher)
    await world.ask(late, teacher)
    assert (await world.decline(teacher, early)).outcome is Answered.DONE
    assert (await world.decline(teacher, late)).outcome is Answered.DONE

    world.later(ANSWER_WITHIN - timedelta(minutes=1))
    assert (await world.approve(teacher, early)).outcome is Answered.DONE
    world.later(timedelta(minutes=2))
    assert (await world.approve(teacher, late)).outcome is Answered.GONE

    assert world.links.students_of(teacher.id) == [early.id]


async def test_decline_leaves_the_list_and_undo_brings_it_back(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)

    declined = await world.decline(teacher, student)
    again = await world.decline(teacher, student)  # idempotent
    assert (declined, again) == (Answer(Answered.DONE, "Ash", 0),) * 2
    assert (await world.waiting(teacher)).total == 0

    assert await world.reopen(teacher, student) == Answer(Answered.DONE, "Ash", 1)
    assert [r.student_id for r in (await world.waiting(teacher)).requests] == [student.id]
    assert world.requests.writes == ["ask", "decline", "reopen"]


async def test_a_decline_tells_nobody_and_shows_the_student_nothing(world: World) -> None:
    """The structural check of spec §7: swap `declined` for `waiting` and every surface the
    student can read gives the same output."""
    teacher, other = world.teacher("Anna"), world.teacher("Boris")
    student = world.student()
    await world.ask(student, teacher)

    async def seen() -> tuple[object, ...]:
        return (
            await world.choices(student),
            await world.mine(student),
            (await world.ask(student, teacher)),
        )

    before = await seen()
    sent = len(world.notifier.asked)
    await world.decline(teacher, student)

    assert await seen() == before
    assert len(world.notifier.asked) == sent
    assert world.notifier.delivered == []
    assert other.id in {c.id for c in (await world.choices(student)).offer}

    world.later(ANSWER_WITHIN + A_MOMENT)  # and the same again once the week is over
    after_week = await seen()
    world.requests.rows[(student.id, teacher.id)].state = RequestState.WAITING
    assert await seen() == after_week


# Confirm all


async def test_confirm_all_skips_declined_late_and_over_cap(world: World) -> None:
    teacher = world.teacher()
    first, second, declined, third = (world.student(n) for n in ("A", "B", "No", "C"))
    for student in (first, second, declined, third):
        await world.ask(student, teacher)
    await world.decline(teacher, declined)
    as_of = (await world.waiting(teacher)).as_of
    late = world.student("Late")
    await world.ask(late, teacher)  # a second after the list was drawn

    done = await world.requests.approve_all(teacher.id, as_of, RequestCaps(students=2), NOW)

    assert done == ApprovedAll(approved=2, left=2)  # oldest first, as many as fit
    assert world.links.students_of(teacher.id) == [first.id, second.id]
    assert world.state(declined, teacher) is RequestState.DECLINED
    assert world.state(third, teacher) is RequestState.WAITING
    assert world.state(late, teacher) is RequestState.WAITING


async def test_the_count_before_a_moment_is_who_was_on_that_list(world: World) -> None:
    """What the confirm step of "Confirm all" names: not who has asked since."""
    teacher = world.teacher()
    for name in ("A", "B"):
        await world.ask(world.student(name), teacher)
    page = await world.waiting(teacher)
    late = world.student("Late")
    await world.ask(late, teacher)

    then = await world.waiting(teacher, before=page.as_of)

    assert (then.total, then.requests) == (2, page.requests)
    assert (await world.waiting(teacher)).total == 3
    assert await world.approve_all(teacher, page.as_of) == ApprovedAll(then.total, left=1)
    assert world.state(late, teacher) is RequestState.WAITING


async def test_confirm_all_through_the_use_case(world: World) -> None:
    teacher = world.teacher()
    students = [world.student(f"S{n}") for n in range(3)]
    for student in students:
        await world.ask(student, teacher)
        world.without_the_note(student, teacher)
    page = await world.waiting(teacher)

    done = await world.approve_all(teacher, page.as_of)

    assert done == ApprovedAll(approved=3, left=0)
    assert world.links.students_of(teacher.id) == [s.id for s in students]
    assert all(not r.quiet_note_agreed and not r.is_primary for r in world.links.rows.values())
    assert await world.approve_all(teacher, page.as_of) == ApprovedAll(0, 0)


# Withdrawing


async def test_withdraw_removes_the_line_and_tells_no_one(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    sent = len(world.notifier.asked)

    assert await world.withdraw(student, teacher) == Withdrawn(removed=True, linked=False)
    assert await world.withdraw(student, teacher) == Withdrawn(removed=False, linked=False)

    assert (await world.mine(student)).asked == ()
    assert (await world.waiting(teacher)).total == 0
    assert len(world.notifier.asked) == sent
    assert (await world.approve(teacher, student)).outcome is Answered.GONE
    assert (await world.ask(student, teacher)).state is AskState.RECENT


async def test_withdraw_looks_the_same_after_a_quiet_no(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.decline(teacher, student)

    assert await world.withdraw(student, teacher) == Withdrawn(removed=True, linked=False)
    assert (await world.reopen(teacher, student)).outcome is Answered.GONE


async def test_withdraw_after_the_yes_says_linked(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.approve(teacher, student)

    assert await world.withdraw(student, teacher) == Withdrawn(removed=False, linked=True)
    assert (student.id, teacher.id) in world.links.rows


# A removed link closes the request


@pytest.mark.parametrize("by", ["student", "teacher"])
async def test_unlink_closes_the_request_for_good(world: World, by: str) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.approve(teacher, student)

    if by == "student":
        await RemoveTeacher(world.links, cities()).execute(Principal(student), teacher.id)
    else:
        await RemoveStudent(world.links).execute(Principal(teacher), student.id)

    assert world.state(student, teacher) is RequestState.WITHDRAWN
    assert (await world.approve(teacher, student)).outcome is Answered.GONE  # an old "Yes"
    assert world.links.rows == {}
    assert (await world.ask(student, teacher)).state is AskState.RECENT


async def test_unlinking_a_personal_link_closes_a_waiting_request(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    world.links.add(student.id, teacher.id)  # the two linked by the teacher's own link

    await RemoveStudent(world.links).execute(Principal(teacher), student.id)

    assert (await world.approve(teacher, student)).outcome is Answered.GONE
    assert world.links.rows == {}


# Validity is a join, not a cleanup


async def test_a_student_who_left_is_gone_and_a_rejoin_revives_nothing(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)

    del world.shalas.students_rows[(world.shala, student.id)]
    assert (await world.waiting(teacher)).total == 0
    assert (await world.mine(student)).asked == ()

    world.shalas.add_student(world.shala, student.id)  # by the wall QR again
    assert (await world.waiting(teacher)).total == 0
    assert (await world.approve(teacher, student)).outcome is Answered.GONE
    assert (await world.ask(student, teacher)).state is AskState.RECENT  # no way around the 30 days
    assert world.state(student, teacher) is RequestState.WAITING  # nothing was written


async def test_a_student_who_became_staff_is_gone(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)

    world.shalas.add_staff(world.shala, student.id, ASSISTANT)

    assert (await world.waiting(teacher)).total == 0
    assert (await world.approve(teacher, student)).outcome is Answered.GONE


async def test_a_teacher_without_the_role_sees_nothing_and_the_student_still_waits(
    world: World,
) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    seat = world.shalas.staff[(world.shala, teacher.id)]

    seat.roles = frozenset({ASSISTANT})
    assert (await world.waiting(teacher)).total == 0
    assert (await world.approve(teacher, student)).outcome is Answered.GONE
    assert [a.teacher_id for a in (await world.mine(student)).asked] == [teacher.id]
    assert (await world.choices(student)).waiting == (TeacherChoice(teacher.id, "Anna"),)

    seat.roles = frozenset({TEACHER})  # the role came back: the same row counts again
    assert (await world.waiting(teacher)).total == 1
    assert (await world.approve(teacher, student)).outcome is Answered.DONE


async def test_a_deleted_shala_or_account_takes_the_request(world: World) -> None:
    teacher, student, other = world.teacher(), world.student("Ash"), world.student("Bea")
    await world.ask(student, teacher)
    await world.ask(other, teacher)

    await world.storage.repo.delete(other.id)
    assert [r.student_id for r in (await world.waiting(teacher)).requests] == [student.id]

    world.shalas._drop(world.shala)  # pyright: ignore[reportPrivateUsage]
    assert (await world.waiting(teacher)).total == 0
    assert (await world.mine(student)).asked == ()


# The lists


async def test_my_requests_and_who_waits_for_me(world: World) -> None:
    anna, boris = world.teacher("Anna"), world.teacher("Boris")
    student = world.student()
    await world.ask(student, anna)
    await world.ask(student, boris)

    mine = await world.mine(student)

    assert mine.asked == (
        AskedTeacher(anna.id, "Anna", world.shala, "Ashtanga Almaty"),
        AskedTeacher(boris.id, "Boris", world.shala, "Ashtanga Almaty"),
    )
    assert mine.waiting == 0
    assert (await world.mine(anna)).waiting == 1
    assert (await world.mine(anna)).asked == ()


async def test_the_waiting_list_pages_oldest_first(world: World) -> None:
    teacher = world.teacher()
    students = [world.student(f"S{n}") for n in range(5)]
    for student in students:
        await world.ask(student, teacher)

    first = await world.waiting(teacher, 0, 2)
    last = await world.waiting(teacher, 4, 2)
    one = await world.waiting(teacher, 0, 10, student=students[3].id)
    nobody = await world.waiting(teacher, 0, 10, student=uuid4())

    assert [r.name for r in first.requests] == ["S0", "S1"]
    assert [r.name for r in last.requests] == ["S4"]
    assert first.total == last.total == one.total == nobody.total == 5
    assert [(r.student_id, r.shala_name) for r in one.requests] == [
        (students[3].id, "Ashtanga Almaty")
    ]
    assert nobody.requests == ()


async def test_nobody_but_the_asked_teacher_sees_or_answers(world: World) -> None:
    """Q322: not the owner, not a manager, not another teacher of the same shala."""
    teacher, student = world.teacher(), world.student()
    manager, colleague = world.person("Manager"), world.teacher("Colleague")
    world.shalas.add_staff(world.shala, manager.id, ADMIN, TEACHER)
    await world.ask(student, teacher)

    for other in (world.owner, manager, colleague):
        assert (await world.waiting(other)).total == 0
        assert (await world.mine(other)).waiting == 0
        assert await world.approve(other, student) == Answer(Answered.GONE)
        assert await world.decline(other, student) == Answer(Answered.GONE)

    assert world.state(student, teacher) is RequestState.WAITING
    assert world.links.rows == {}


# A request is not a link


@pytest.mark.parametrize("state", [RequestState.WAITING, RequestState.DECLINED])
async def test_a_waiting_or_declined_request_grants_nothing(
    world: World, state: RequestState
) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    world.requests.rows[(student.id, teacher.id)].state = state
    view = world.storage.teacher_view

    links = await GetLinks(world.links).execute(Principal(teacher))
    page, total = await GetStudents(view, world.clock).execute(Principal(teacher), 0, 20)

    assert links.students == ()
    assert (await GetLinks(world.links).execute(Principal(student))).teachers == ()
    assert (page, total) == ((), 0)
    with pytest.raises(NotLinked):  # the card is `not_linked`
        await GetStudent(view, world.clock, Track(_catalog())).execute(
            Principal(teacher), student.id
        )
    assert await world.storage.progression.for_teacher(teacher.id, student.id) is None  # no mark
    accounts = world.storage.repo
    assert isinstance(accounts, FollowingAccounts)  # the account load, as the middleware's
    assert accounts.inputs(teacher).teaches is False  # no announcement audience, no Keep offer
    assert accounts.inputs(student).main_teacher is None  # no moon effect


def _catalog():
    from tests.domain.test_practice import catalog

    return catalog()


# The closing notes' read (the tick sends them in the next slice)


async def test_confirmed_is_due_at_once_and_only_until_it_is_in_the_ledger(world: World) -> None:
    teacher, student = world.teacher(), world.student(locale="ru", zone="Asia/Almaty")
    await world.ask(student, teacher)
    assert await world.requests.due(world.clock.now(), 100) == []

    await world.approve(teacher, student)
    [due] = await world.requests.due(world.clock.now(), 100)

    row = world.requests.rows[(student.id, teacher.id)]
    assert (due.id, due.closing, due.student_id) == (row.id, Closing.CONFIRMED, student.id)
    assert (due.locale, due.zone, due.teacher_name) == ("ru", "Asia/Almaty", "Anna")
    assert (due.teacher_id, due.shala_id, due.my_teachers) == (teacher.id, world.shala, 1)

    from tristhana.domain.teacher_requests import request_key

    ledger = world.storage.notifications
    assert await ledger.claim(student.id, request_key(due.id), "request", date(2026, 11, 17))
    await ledger.finish(student.id, request_key(due.id), "sent")
    assert await world.requests.due(world.clock.now(), 100) == []


async def test_a_quiet_no_and_silence_fall_due_in_the_same_run(world: World) -> None:
    teacher = world.teacher()
    silent, declined, gone = world.student("Silent"), world.student("No"), world.student("Left")
    for student in (silent, declined, gone):
        await world.ask(student, teacher)
    await world.decline(teacher, declined)  # on day 0
    del world.shalas.students_rows[(world.shala, gone.id)]

    world.later(ANSWER_WITHIN - timedelta(minutes=1))
    assert await world.requests.due(world.clock.now(), 100) == []
    world.later(timedelta(minutes=2))
    due = await world.requests.due(world.clock.now(), 100)

    assert {d.student_id for d in due} == {silent.id, declined.id}  # the one who left: no note
    assert {d.closing for d in due} == {Closing.NO_ANSWER}


async def test_prune_takes_rows_older_than_thirty_days(world: World) -> None:
    teacher, old, new = world.teacher(), world.student("Old"), world.student("New")
    await world.ask(old, teacher)
    world.later(timedelta(days=20))
    await world.ask(new, teacher)
    world.later(timedelta(days=10) + A_MOMENT)

    assert await world.requests.prune(world.clock.now() - KEEP) == 1

    assert set(world.requests.rows) == {(new.id, teacher.id)}


# Policies: a role by action matrix


def _memberships() -> list[Membership]:
    shala = UUID(int=7)
    roles = list(ShalaRole)
    staff = [
        Membership(shala, owner, frozenset(chosen), False)
        for owner in (False, True)
        for n in range(len(roles) + 1)
        for chosen in itertools.combinations(roles, n)
    ]
    return [*staff, Membership(shala, False, frozenset(), True)]


def test_only_a_student_asks_and_only_the_teacher_role_is_asked() -> None:
    everyone = [*_memberships(), None]

    for actor, target in itertools.product(everyone, everyone):
        expected = (
            actor is not None
            and actor.student
            and target is not None
            and not target.student
            and TEACHER in target.roles
        )
        assert can_ask_teacher(actor, target) is expected, (actor, target)


@pytest.mark.parametrize(
    ("roles", "owner", "asked"),
    [
        ({TEACHER}, False, True),
        ({TEACHER, ADMIN}, False, True),
        ({TEACHER}, True, True),  # an owner who teaches
        (set[ShalaRole](), True, False),  # an owner counts only with the role
        ({ADMIN}, True, False),
        ({ASSISTANT}, False, False),
        ({ADMIN}, False, False),
        ({OFFICE}, False, False),
        ({ASSISTANT, ADMIN, OFFICE}, False, False),
    ],
)
def test_who_can_be_asked(roles: set[ShalaRole], owner: bool, asked: bool) -> None:
    shala = UUID(int=7)
    student = Membership(shala, False, frozenset(), True)

    assert can_ask_teacher(student, Membership(shala, owner, frozenset(roles), False)) is asked


def test_only_the_two_people_act_on_a_request() -> None:
    accounts = InMemoryAccounts()
    teacher, owner, student = (add_person(accounts, n) for n in ("1", "2", "3"))

    assert can_answer_request(teacher, teacher.id)
    assert not can_answer_request(owner, teacher.id)  # an owner can't answer for a teacher
    assert not can_answer_request(student, teacher.id)
    assert can_withdraw_request(student, student.id)
    assert not can_withdraw_request(teacher, student.id)
    assert not can_withdraw_request(owner, student.id)
