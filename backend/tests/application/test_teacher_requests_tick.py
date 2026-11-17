"""The tick's closing notes for teacher requests (ID-07 spec §3, §7, §8; ADR-0046): one
silent note per request, from the live rows and the delivery ledger (category `request`, key
`req:<id>`). "Confirmed" goes out as soon as the link exists; "no answer yet" at day 7, for a
quiet "no" and for silence in the same run and with the same content. The tick also prunes
rows older than 30 days."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from tests.application.test_teacher_requests import World
from tests.fakes import FakeCalculator, cities
from tristhana.application.ports.notifications import (
    DeliveryResult,
    DeliveryStatus,
    Recipient,
    RequestClosed,
)
from tristhana.application.tick import DUE_REQUESTS, RunTick, TickResult
from tristhana.domain.teacher_requests import ANSWER_WITHIN, KEEP, Closing, request_key

assert timedelta(days=30) == KEEP  # the prune test below counts in days

A_MOMENT = timedelta(seconds=1)


@dataclass
class Claims:
    """The ledger's claims as the tick made them: (account, key, category, local date)."""

    seen: list[tuple[UUID, str, str, date]] = field(
        default_factory=list[tuple[UUID, str, str, date]]
    )

    def watch(self, ledger: Any) -> None:
        claim = ledger.claim

        async def recorded(account_id: UUID, key: str, category: str, local_date: date) -> bool:
            self.seen.append((account_id, key, category, local_date))
            return await claim(account_id, key, category, local_date)

        ledger.claim = recorded

    @property
    def requests(self) -> list[tuple[UUID, str, str, date]]:
        return [c for c in self.seen if c[2] == "request"]


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def claims(world: World) -> Claims:
    found = Claims()
    found.watch(world.storage.notifications)
    return found


def _tick(world: World) -> RunTick:
    return RunTick(
        world.clock,
        cities(),
        world.storage.moon,
        FakeCalculator(),
        world.storage.notifications,
        world.notifier,
        requests=world.requests,
    )


async def _run(world: World, budget: timedelta = timedelta(seconds=30)) -> TickResult:
    return await _tick(world).execute(budget)


def _closed(world: World) -> list[tuple[Recipient, RequestClosed]]:
    return [(r, n) for r, n in world.notifier.delivered if isinstance(n, RequestClosed)]


def _telegram_id(world: World, account_id: UUID) -> str:
    [found] = [
        k.provider_user_id for k, v in world.storage.repo.identities.items() if v == account_id
    ]
    return found


async def test_a_waiting_request_sends_nothing(world: World, claims: Claims) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    world.later(ANSWER_WITHIN - A_MOMENT)

    result = await _run(world)

    assert _closed(world) == []
    assert claims.requests == []
    assert result.sent == 0


async def test_the_yes_reaches_the_student_in_the_next_tick(world: World, claims: Claims) -> None:
    teacher = world.teacher("Anna", locale="en")
    student = world.student("Ash", locale="ru", zone="Pacific/Kiritimati")  # UTC+14
    await world.ask(student, teacher)
    await world.approve(teacher, student)
    row = world.requests.rows[(student.id, teacher.id)]

    result = await _run(world)

    [(recipient, note)] = _closed(world)
    assert recipient == Recipient(_telegram_id(world, student.id), "ru")  # the student's language
    assert note == RequestClosed(Closing.CONFIRMED, teacher.id, "Anna", world.shala, False)
    # 10:30 UTC on 17 Nov is already 18 Nov on Kiritimati: the ledger's date is the student's.
    assert claims.requests == [(student.id, request_key(row.id), "request", date(2026, 11, 18))]
    assert world.storage.notifications.deliveries[(student.id, request_key(row.id))]["status"] == (
        "sent"
    )
    assert result.sent == 1


async def test_a_student_without_a_zone_is_dated_in_utc(world: World, claims: Claims) -> None:
    teacher, student = world.teacher(), world.student(zone=None)
    await world.ask(student, teacher)
    await world.approve(teacher, student)

    await _run(world)

    assert [c[3] for c in claims.requests] == [date(2026, 11, 17)]


async def test_a_note_is_claimed_once_across_two_runs(world: World, claims: Claims) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.approve(teacher, student)

    await _run(world)
    second = await _run(world)
    world.later(ANSWER_WITHIN + A_MOMENT)  # and day 7 owes a confirmed student nothing
    third = await _run(world)

    assert len(_closed(world)) == 1
    assert len(claims.requests) == 1
    assert (second.sent, third.sent) == (0, 0)


async def test_two_runs_at_once_send_one_note(world: World) -> None:
    """The second run read the same due row before the first finished: the claim decides."""
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.approve(teacher, student)
    [due] = await world.requests.due(world.clock.now(), DUE_REQUESTS)
    ledger = world.storage.notifications
    assert await ledger.claim(student.id, request_key(due.id), "request", date(2026, 11, 17))
    world.requests.notifications = None  # the read no longer sees the ledger: a stale read

    result = await _run(world)

    assert _closed(world) == []
    assert (result.sent, result.skipped) == (0, 1)


async def test_a_quiet_no_and_silence_get_the_same_note_in_the_same_run(
    world: World, claims: Claims
) -> None:
    teacher = world.teacher("Anna")
    silent, declined = world.student("Silent"), world.student("No")
    await world.ask(silent, teacher)
    await world.ask(declined, teacher)
    await world.decline(teacher, declined)  # on day 0

    world.later(ANSWER_WITHIN - timedelta(minutes=1))
    await _run(world)
    assert _closed(world) == []  # a note before day 7 could only mean a "no"

    world.later(timedelta(minutes=2))
    await _run(world)

    notes = {r.telegram_id: n for r, n in _closed(world)}
    assert set(notes) == {_telegram_id(world, silent.id), _telegram_id(world, declined.id)}
    expected = RequestClosed(Closing.NO_ANSWER, teacher.id, "Anna", world.shala, False)
    assert list(notes.values()) == [expected, expected]
    assert {c[2] for c in claims.requests} == {"request"}
    assert len(world.notifier.asked) == 2  # the teacher got the two asks and nothing since


async def test_no_closing_note_goes_to_a_teacher(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.decline(teacher, student)
    world.later(ANSWER_WITHIN + A_MOMENT)

    await _run(world)

    assert [r.telegram_id for r, _ in _closed(world)] == [_telegram_id(world, student.id)]


async def test_make_main_is_offered_only_from_the_second_teacher(world: World) -> None:
    first, second = world.teacher("Anna"), world.teacher("Boris")
    student = world.student()
    await world.ask(student, first)
    await world.approve(first, student)
    await _run(world)
    await world.ask(student, second)
    await world.approve(second, student)

    await _run(world)

    assert [(n.teacher_name, n.make_main) for _, n in _closed(world)] == [
        ("Anna", False),
        ("Boris", True),
    ]


async def test_no_answer_never_offers_make_main(world: World) -> None:
    linked, asked = world.teacher("Anna"), world.teacher("Boris")
    student = world.student()
    world.links.add(student.id, linked.id)
    world.links.add(student.id, world.person("Vera").id)
    await world.ask(student, asked)
    world.later(ANSWER_WITHIN + A_MOMENT)

    await _run(world)

    [(_, note)] = _closed(world)
    assert (note.closing, note.make_main) == (Closing.NO_ANSWER, False)


async def test_a_student_who_left_gets_no_note(world: World, claims: Claims) -> None:
    teacher = world.teacher()
    left, stayed = world.student("Left"), world.student("Stayed")
    await world.ask(left, teacher)
    await world.ask(stayed, teacher)
    await world.approve(teacher, left)
    del world.shalas.students_rows[(world.shala, left.id)]
    world.later(ANSWER_WITHIN + A_MOMENT)

    await _run(world)

    assert [r.telegram_id for r, _ in _closed(world)] == [_telegram_id(world, stayed.id)]
    assert [c[0] for c in claims.requests] == [stayed.id]


async def test_a_withdrawn_request_gets_no_note(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.withdraw(student, teacher)
    world.later(ANSWER_WITHIN + A_MOMENT)

    await _run(world)

    assert _closed(world) == []


async def test_a_blocked_student_is_marked_unreachable_and_not_tried_again(
    world: World,
) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.approve(teacher, student)
    world.notifier.outcomes.append(DeliveryResult(DeliveryStatus.BLOCKED))

    result = await _run(world)
    again = await _run(world)

    assert student.id in world.storage.notifications.unreachable
    assert (result.blocked, result.sent, again.blocked, again.sent) == (1, 0, 0, 0)
    assert len(_closed(world)) == 1


async def test_a_failed_send_is_tried_again_by_a_later_tick(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.approve(teacher, student)
    world.notifier.outcomes.append(DeliveryResult(DeliveryStatus.FAILED))

    first = await _run(world)
    second = await _run(world)

    assert (first.failed, first.sent, second.sent) == (1, 0, 1)
    assert len(_closed(world)) == 2


async def test_out_of_time_claims_nothing_and_leaves_the_rest(world: World, claims: Claims) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.approve(teacher, student)

    result = await _run(world, timedelta(0))

    assert result.stopped_early is True
    assert (_closed(world), claims.requests) == ([], [])
    assert "due" not in world.requests.calls  # not even the read

    await _run(world)

    assert len(_closed(world)) == 1


async def test_a_rate_limit_stops_the_run_and_the_next_tick_resumes(world: World) -> None:
    teacher = world.teacher()
    students = [world.student(name) for name in ("A", "B", "C")]
    for student in students:
        await world.ask(student, teacher)
        await world.approve(teacher, student)
    world.notifier.outcomes.extend(
        [DeliveryResult(DeliveryStatus.SENT), DeliveryResult(DeliveryStatus.RETRY_AFTER, 5.0)]
    )

    first = await _run(world)

    assert (first.sent, first.failed, first.stopped_early) == (1, 1, True)
    assert len(_closed(world)) == 2  # the third was never tried

    second = await _run(world)

    assert (second.sent, second.stopped_early) == (2, False)
    sent_to = [r.telegram_id for r, _ in _closed(world)]
    assert set(sent_to) == {_telegram_id(world, s.id) for s in students}


async def test_the_tick_reads_a_bounded_batch(world: World) -> None:
    seen: list[tuple[datetime, int]] = []
    due = world.requests.due

    async def recorded(now: datetime, limit: int) -> Any:
        seen.append((now, limit))
        return await due(now, limit)

    world.requests.due = recorded  # type: ignore[method-assign]

    await _run(world)

    assert seen == [(world.clock.now(), DUE_REQUESTS)]
    assert DUE_REQUESTS == 500  # spec §7: at most 500 notes a run


async def test_the_tick_prunes_rows_older_than_thirty_days(world: World) -> None:
    teacher, old, new = world.teacher(), world.student("Old"), world.student("New")
    await world.ask(old, teacher)
    world.later(timedelta(days=20))
    await world.ask(new, teacher)
    world.later(timedelta(days=10) + A_MOMENT)  # 30 days and a moment after the first ask

    result = await _run(world)

    assert set(world.requests.rows) == {(new.id, teacher.id)}
    assert result.pruned == 1


async def test_out_of_time_prunes_nothing(world: World) -> None:
    teacher, old = world.teacher(), world.student("Old")
    await world.ask(old, teacher)
    world.later(KEEP + A_MOMENT)

    await _run(world, timedelta(0))

    assert "prune" not in world.requests.calls


async def test_a_tick_without_the_request_port_still_runs(world: World) -> None:
    teacher, student = world.teacher(), world.student()
    await world.ask(student, teacher)
    await world.approve(teacher, student)
    tick = RunTick(
        world.clock,
        cities(),
        world.storage.moon,
        FakeCalculator(),
        world.storage.notifications,
        world.notifier,
    )

    result = await tick.execute(timedelta(seconds=30))

    assert _closed(world) == []
    assert result.stopped_early is False


def test_the_app_wires_the_request_port_into_the_tick() -> None:
    from typing import cast

    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from tests.shala_fakes import shala_storage
    from tristhana.main import create_app
    from tristhana.settings import Settings

    storage = shala_storage()
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr("123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"),
    )
    app = create_app(settings, storage)

    with TestClient(app):
        tick = cast(RunTick, app.state.run_tick)

    assert tick._requests is storage.teacher_requests  # pyright: ignore[reportPrivateUsage]
