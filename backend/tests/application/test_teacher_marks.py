"""Teacher marks' use cases on scripted ports (PR-08 Phase 3, spec §3, §9, ADR-0037): the policy
(the link's teacher, one hop, one way), the SQL guard first and the policy second, what each
refusal is, one silent note on success and none on a refusal, a teacher's reply that can't vary
with anything hidden, the student's today (never the teacher's), and `next_asanas` on the card.
A frozen clock throughout."""

import inspect
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from tests.domain.test_practice import catalog
from tests.fakes import FakeNotifier, FixedClock, InMemoryAccounts
from tests.teacher_link_fakes import add_person
from tests.teacher_mark_fakes import ScriptedMarks
from tests.teacher_view_fakes import ScriptedTeacherView
from tristhana.application.policies import (
    NotAllowed,
    Principal,
    can_mark_progression,
    can_view_milestones,
    can_view_progression,
)
from tristhana.application.ports.notifications import (
    AsanaMarked,
    DeliveryResult,
    DeliveryStatus,
    Recipient,
)
from tristhana.application.ports.progression import MarkLink, ProgressionView, TeacherMarkView
from tristhana.application.ports.teacher_links import NotLinked
from tristhana.application.ports.teacher_view import SharedDetail, SharedLog, StudentLink
from tristhana.application.progression import ProgressionChanged
from tristhana.application.teacher_marks import Marked, MarkForStudent
from tristhana.application.teacher_view import GetStudent
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.progression import (
    STANDING_ONLY,
    Celebration,
    CelebrationKind,
    Earlier,
    EventKind,
    Position,
    Progression,
    Track,
)

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
LINKED = date(2026, 6, 1)
K = CelebrationKind
KAPOTASANA_B = Position("intermediate", "kapotasana-b")
SUPTA_VAJRASANA = Position("intermediate", "supta-vajrasana")
BAKASANA_B = Position("intermediate", "bakasana-b")
BHARADVAJASANA = Position("intermediate", "bharadvajasana")
ARDHA_MATSYENDRASANA = Position("intermediate", "ardha-matsyendrasana")
OMKARASANA = Position("advanced-b", "omkarasana")
TRACK = Track(catalog())


class World:
    def __init__(self, instant: datetime = NOW) -> None:
        self.clock = FixedClock(instant)
        self.accounts = InMemoryAccounts(clock=self.clock)
        self.teacher = add_person(self.accounts, "1", "Лена", "ru", "Pacific/Kiritimati")
        self.student = add_person(self.accounts, "2", "Anna", "en", "Asia/Almaty")
        self.repo = ScriptedMarks()
        self.notifier = FakeNotifier()

    def link(
        self,
        teacher: UUID | None = None,
        zone: str | None = "Asia/Almaty",
        locale: Locale = "en",
        telegram_id: str | None = "2",
    ) -> MarkLink:
        return MarkLink(
            teacher_id=teacher or self.teacher.id,
            student_id=self.student.id,
            timezone=zone,
            locale=locale,
            telegram_id=telegram_id,
        )

    def found(
        self,
        position: Position | None = KAPOTASANA_B,
        earlier: frozenset[Position] | None = None,
        link: MarkLink | None = None,
        last_event_id: int = 41,
    ) -> None:
        progression = (
            Progression(position, frozenset({"drop-backs"}), last_event_id)
            if position is not None
            else None
        )
        seen = earlier if earlier is not None else frozenset({position} if position else set())
        view = ProgressionView(progression, Earlier(seen, frozenset({"drop-backs"})))
        self.repo.found = TeacherMarkView(link or self.link(), view)

    def use_case(self) -> MarkForStudent:
        return MarkForStudent(self.repo, TRACK, self.clock, self.notifier)

    async def mark(
        self,
        target: Position = SUPTA_VAJRASANA,
        seen: Position = KAPOTASANA_B,
        actor: Account | None = None,
    ) -> Marked:
        principal = Principal(actor or self.teacher)
        return await self.use_case().execute(principal, self.student.id, seen, target)


@pytest.fixture
def world() -> World:
    return World()


# The policy: the link's teacher, one hop, one way


def _mark_link(teacher: UUID, student: UUID) -> MarkLink:
    return MarkLink(
        teacher_id=teacher, student_id=student, timezone=None, locale="en", telegram_id=None
    )


def _person(name: str) -> Account:
    return add_person(InMemoryAccounts(), str(uuid4().int)[:9], name)


def test_the_links_teacher_may_mark() -> None:
    teacher, student = _person("Лена"), _person("Anna")

    assert can_mark_progression(teacher, _mark_link(teacher.id, student.id))


def test_an_assistant_the_student_added_is_a_teacher_like_any_other() -> None:
    """Being on the student's list is the whole rule (Q1)."""
    lead, assistant, student = _person("Лена"), _person("Dmitry"), _person("Anna")
    lead_link = _mark_link(lead.id, student.id)
    assistant_link = _mark_link(assistant.id, student.id)

    assert can_mark_progression(assistant, assistant_link)
    assert not can_mark_progression(assistant, lead_link)


@pytest.mark.parametrize(
    "who",
    ["the student", "a third party", "a co-student", "the teacher's teacher", "shala staff"],
)
def test_no_one_else_may_mark(who: str) -> None:
    """Rights go one hop: none of these is the link's teacher, whatever else links them."""
    teacher, student, other = _person("Лена"), _person("Anna"), _person(who)
    actor = student if who == "the student" else other

    assert not can_mark_progression(actor, _mark_link(teacher.id, student.id))


def test_the_direction_matters_in_a_cycle() -> None:
    """Anna teaches Лена too: Лена's link as Anna's student gives Лена no right over Anna."""
    lena, anna = _person("Лена"), _person("Anna")
    lena_teaches_anna = _mark_link(lena.id, anna.id)
    anna_teaches_lena = _mark_link(anna.id, lena.id)

    assert can_mark_progression(lena, lena_teaches_anna)
    assert not can_mark_progression(lena, anna_teaches_lena)
    assert not can_mark_progression(anna, lena_teaches_anna)


def test_progression_and_milestones_stay_owner_only() -> None:
    teacher, student = _person("Лена"), _person("Anna")

    assert not can_view_progression(teacher, student)
    assert not can_view_milestones(teacher, student)


# Built with the progression port, the track, a clock and the notifier only


def test_the_use_case_takes_four_things_and_nothing_else() -> None:
    assert list(inspect.signature(MarkForStudent).parameters) == [
        "progression",
        "track",
        "clock",
        "notifier",
    ]


# Success


async def test_a_mark_is_one_read_one_guarded_write_and_one_note(world: World) -> None:
    world.found()

    marked = await world.mark()

    assert marked == Marked(KAPOTASANA_B, SUPTA_VAJRASANA)
    assert world.repo.calls == ["for_teacher", "apply"]
    [applied] = world.repo.applied
    assert applied["account_id"] == world.student.id
    assert applied["expected"] == 41
    assert applied["marked_by"] == world.teacher.id
    assert applied["before"] == KAPOTASANA_B
    assert applied["link_teacher"] == world.teacher.id
    change = applied["change"]
    assert change.kind is EventKind.GIVEN
    assert (change.before, change.after) == (KAPOTASANA_B, SUPTA_VAJRASANA)
    assert change.state.items == {"drop-backs"}


async def test_the_note_goes_to_the_student_in_their_locale_with_the_celebration(
    world: World,
) -> None:
    world.found(link=world.link(locale="ru", telegram_id="2"))

    await world.mark(BHARADVAJASANA)

    [(recipient, teacher, mark)] = world.notifier.marked
    assert recipient == Recipient("2", "ru")
    assert teacher == "Лена"  # the teacher's own name, for "Marked by …"
    assert mark == AsanaMarked(
        101,
        (Celebration(K.NEW_ASANA, "intermediate", "bharadvajasana", first=SUPTA_VAJRASANA),),
        BHARADVAJASANA,
    )


async def test_a_mark_held_before_sends_the_note_with_no_celebration(world: World) -> None:
    world.found(earlier=frozenset({KAPOTASANA_B, BHARADVAJASANA}))

    await world.mark(BAKASANA_B)

    [(_, _, mark)] = world.notifier.marked
    assert mark.celebrations == ()
    assert mark.target == BAKASANA_B


async def test_a_range_into_intermediate_sends_the_series_lines(world: World) -> None:
    before = Position("primary", "urdhva-mukha-paschimottanasana")
    world.found(before)

    await world.mark(Position("intermediate", "krounchasana"), seen=before)

    [(_, _, mark)] = world.notifier.marked
    assert [c.kind for c in mark.celebrations] == [
        K.NEW_ASANA,
        K.SERIES_COMPLETE,
        K.SERIES_BEGINS,
    ]


@pytest.mark.parametrize("status", [DeliveryStatus.BLOCKED, DeliveryStatus.FAILED])
async def test_an_undelivered_note_still_marks(world: World, status: DeliveryStatus) -> None:
    world.found()
    world.notifier.mark_outcomes.append(DeliveryResult(status))

    assert await world.mark() == Marked(KAPOTASANA_B, SUPTA_VAJRASANA)


async def test_the_teachers_reply_cant_tell_first_time_from_held_before() -> None:
    first, again = World(), World()
    first.found()
    again.found(earlier=frozenset({KAPOTASANA_B, SUPTA_VAJRASANA, BHARADVAJASANA}))

    assert await first.mark() == await again.mark()
    assert first.notifier.marked[0][2].celebrations != again.notifier.marked[0][2].celebrations


async def test_the_teachers_reply_cant_tell_delivered_from_blocked() -> None:
    sent, blocked = World(), World()
    sent.found()
    blocked.found()
    blocked.notifier.mark_outcomes.append(DeliveryResult(DeliveryStatus.BLOCKED))

    assert await sent.mark() == await blocked.mark()


def test_marked_carries_what_the_teacher_saw_and_the_target_only() -> None:
    assert [f for f in Marked.__dataclass_fields__] == ["seen", "target"]


# The student's today, never the teacher's


@pytest.mark.parametrize(
    ("instant", "zone", "day"),
    [
        # 10:30 UTC: Kiritimati (+14) is on Nov 9, Honolulu (-10) still on Nov 8.
        (datetime(2026, 11, 8, 10, 30, tzinfo=UTC), "Pacific/Kiritimati", date(2026, 11, 9)),
        (datetime(2026, 11, 8, 10, 30, tzinfo=UTC), "Pacific/Honolulu", date(2026, 11, 8)),
        (datetime(2026, 11, 8, 18, 20, tzinfo=UTC), "Asia/Kolkata", date(2026, 11, 8)),
        (datetime(2026, 11, 8, 18, 30, tzinfo=UTC), "Asia/Kolkata", date(2026, 11, 9)),
        (datetime(2026, 11, 8, 18, 14, tzinfo=UTC), "Asia/Kathmandu", date(2026, 11, 8)),
        (datetime(2026, 11, 8, 18, 15, tzinfo=UTC), "Asia/Kathmandu", date(2026, 11, 9)),
        (datetime(2026, 10, 24, 22, 30, tzinfo=UTC), "Europe/Berlin", date(2026, 10, 25)),
        (datetime(2026, 11, 8, 18, 59, tzinfo=UTC), "Asia/Almaty", date(2026, 11, 8)),
        (datetime(2026, 11, 8, 21, 0, tzinfo=UTC), "Europe/Moscow", date(2026, 11, 9)),
        (datetime(2026, 11, 9, 4, 59, tzinfo=UTC), "America/New_York", date(2026, 11, 8)),
    ],
)
async def test_occurred_on_is_the_students_local_today(
    instant: datetime, zone: str, day: date
) -> None:
    """The teacher is in Kiritimati: their date never leaks into the student's record."""
    world = World(instant)
    world.found(link=world.link(zone=zone))

    await world.mark()

    assert world.repo.applied[0]["change"].occurred_on == day


async def test_with_no_zone_the_provisional_one_from_the_locale_counts() -> None:
    """RU's provisional zone is Moscow: 21:30 UTC is already the next day there."""
    world = World(datetime(2026, 11, 8, 21, 30, tzinfo=UTC))
    world.found(link=world.link(zone=None, locale="ru"))

    await world.mark()

    assert world.repo.applied[0]["change"].occurred_on == date(2026, 11, 9)


# Refusals: nothing written, nothing sent


async def test_unlinked_is_not_linked(world: World) -> None:
    world.repo.found = None

    with pytest.raises(NotLinked):
        await world.mark()
    assert world.repo.calls == ["for_teacher"]
    assert world.notifier.marked == []


async def test_a_foreign_link_from_the_port_is_not_allowed(world: World) -> None:
    """The SQL guard is the first gate and the policy the second."""
    someone = add_person(world.accounts, "3", "Boris")
    world.found(link=world.link(teacher=someone.id))

    with pytest.raises(NotAllowed):
        await world.mark()
    assert world.repo.applied == []
    assert world.notifier.marked == []


async def test_the_student_acting_on_their_own_card_is_not_allowed(world: World) -> None:
    world.found()

    with pytest.raises(NotAllowed):
        await world.mark(actor=world.student)
    assert world.repo.applied == []


async def test_a_stale_card_is_progression_changed(world: World) -> None:
    world.found(SUPTA_VAJRASANA)  # the student marked it themselves meanwhile

    with pytest.raises(ProgressionChanged):
        await world.mark(BAKASANA_B, seen=KAPOTASANA_B)
    assert world.repo.applied == []
    assert world.notifier.marked == []


@pytest.mark.parametrize(
    "target",
    [
        ARDHA_MATSYENDRASANA,  # a 4th stop
        KAPOTASANA_B,  # the same
        Position("intermediate", "ustrasana"),  # back
        Position("intermediate", "kapotasana-a"),  # not a stop
    ],
)
async def test_a_target_outside_the_next_three_is_progression_changed(
    world: World, target: Position
) -> None:
    """In-range is checked against the card's position; past the API's own 422, only a forged
    or out-of-date bot value can get here."""
    world.found()

    with pytest.raises(ProgressionChanged):
        await world.mark(target)
    assert world.repo.applied == []
    assert world.notifier.marked == []


async def test_an_unset_student_is_progression_changed(world: World) -> None:
    world.found(None)

    with pytest.raises(ProgressionChanged):
        await world.mark(Position("primary", "utthita-hasta-padangusthasana"), STANDING_ONLY)
    assert world.repo.applied == []
    assert world.notifier.marked == []


async def test_at_the_end_of_the_confirmed_series_nothing_can_be_marked(world: World) -> None:
    world.found(OMKARASANA)

    with pytest.raises(ProgressionChanged):
        await world.mark(Position("advanced-c", "anything"), OMKARASANA)
    assert world.repo.applied == []


async def test_a_lost_compare_and_set_is_progression_changed_and_sends_nothing(
    world: World,
) -> None:
    world.found()
    world.repo.result = None

    with pytest.raises(ProgressionChanged):
        await world.mark()
    assert world.repo.calls == ["for_teacher", "apply"]
    assert world.notifier.marked == []


async def test_a_student_with_no_telegram_identity_is_marked_without_a_note(world: World) -> None:
    """Every account today has one; a later web-only account still gets the mark (and sees it
    in My asanas)."""
    world.found(link=world.link(telegram_id=None))

    assert await world.mark() == Marked(KAPOTASANA_B, SUPTA_VAJRASANA)
    assert world.notifier.marked == []


# The card's `next_asanas` (GetStudent with the track injected)


def _detail(position: Position | None, teacher: UUID) -> SharedDetail:
    link = StudentLink(teacher, uuid4(), "Anna", "Asia/Almaty", "en", LINKED)
    return SharedDetail(SharedLog(link, {}), {}, position, True)


@pytest.mark.parametrize(
    ("position", "targets"),
    [
        (KAPOTASANA_B, (SUPTA_VAJRASANA, BAKASANA_B, BHARADVAJASANA)),
        (
            STANDING_ONLY,
            (
                Position("primary", "utthita-hasta-padangusthasana"),
                Position("primary", "ardha-baddha-padmottanasana"),
                Position("primary", "utkatasana"),
            ),
        ),
        (Position("advanced-b", "sama-konasana"), (OMKARASANA,)),
        (OMKARASANA, ()),
        (None, ()),
        (Position("primary", "renamed-asana"), ()),
    ],
    ids=["mid-series", "standing", "near-the-end", "the-end", "unset", "stale"],
)
async def test_the_card_offers_the_next_three_stops(
    world: World, position: Position | None, targets: tuple[Position, ...]
) -> None:
    view = ScriptedTeacherView()
    detail = _detail(position, world.teacher.id)
    view.details[detail.log.link.student_id] = detail

    card = await GetStudent(view, world.clock, TRACK).execute(
        Principal(world.teacher), detail.log.link.student_id
    )

    assert card.next_asanas == targets
    assert card.last_asana == position
    assert len(view.student_calls) == 1  # still one read


async def test_the_card_still_refuses_a_foreign_row(world: World) -> None:
    view = ScriptedTeacherView()
    detail = _detail(KAPOTASANA_B, uuid4())
    view.details[detail.log.link.student_id] = detail

    with pytest.raises(NotAllowed):
        await GetStudent(view, world.clock, TRACK).execute(
            Principal(world.teacher), detail.log.link.student_id
        )


def test_get_student_takes_the_track_beside_the_port_and_the_clock() -> None:
    assert len(inspect.signature(GetStudent).parameters) == 3
