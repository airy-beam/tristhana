"""Teacher marks over the API (PR-08 Phase 3, spec §5, ADR-0037): `next_asanas` on the card;
`POST /me/students/{id}/new-asana` with 200 (the refreshed card), 404 (one body for unknown,
unlinked and reversed ids, and for shala staff with no link), 409 (out of date) and 422 (not
within the next three); a reply that never varies with the student's history or the delivery;
the history's `by`, `by_name`, `undoable` and `marked`; DELETE of a retractable non-latest event.
Real use cases over the in-memory ports, with a frozen clock and a recording notifier."""

import asyncio
import json
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FakeNotifier, FixedClock, InMemoryStorage
from tests.teacher_link_fakes import add_person
from tests.teacher_mark_fakes import MarkingProgression, marking
from tristhana.api.initdata import sign
from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus, Recipient
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider
from tristhana.domain.progression import Change, EventKind, Position, Progression
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ME_TG = 42
STUDENT_TG = 2
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
TODAY = date(2026, 11, 8)
LINKED = date(2026, 6, 1)
CARD = "/api/v1/me/students/{id}"
MARK = "/api/v1/me/students/{id}/new-asana"
MINE = "/api/v1/me/progression"
KAPOTASANA_B = Position("intermediate", "kapotasana-b")
SUPTA_VAJRASANA = Position("intermediate", "supta-vajrasana")
BAKASANA_B = Position("intermediate", "bakasana-b")
BHARADVAJASANA = Position("intermediate", "bharadvajasana")
ITEMS = frozenset({"drop-backs"})


def _auth(user_id: int = ME_TG, name: str = "Лена") -> dict[str, str]:
    profile = {"id": user_id, "first_name": name, "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


def _pos(p: Position) -> dict[str, str | None]:
    return {"series": p.series, "last": p.key}


def _body(seen: Position, to: Position) -> dict[str, Any]:
    return {"from": _pos(seen), "to": _pos(to)}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def repo(storage: InMemoryStorage) -> MarkingProgression:
    return marking(storage)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def api(
    storage: InMemoryStorage,
    repo: MarkingProgression,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    fixed = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: fixed)
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage, notifier)) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage, user_id: int = ME_TG) -> UUID:
    assert api.get("/api/v1/me", headers=_auth(user_id)).status_code == 200
    return storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(user_id))]


async def _seed(repo: MarkingProgression, who: UUID, position: Position) -> int:
    start = Change(EventKind.START, TODAY, Progression(position), after=position)
    first = await repo.apply(who, start, None, who)
    assert first is not None
    item = Change(EventKind.ITEM_GIVEN, TODAY, Progression(position, ITEMS), item="drop-backs")
    second = await repo.apply(who, item, first.id, who)
    assert second is not None
    return second.id


def _student(
    storage: InMemoryStorage,
    me: UUID,
    position: Position | None = KAPOTASANA_B,
    telegram_id: int = STUDENT_TG,
    locale: str = "ru",
) -> Account:
    student = add_person(storage.repo, str(telegram_id), "Anna", locale, "Asia/Almaty")  # type: ignore[arg-type]
    storage.teacher_links.add(student.id, me, linked_on=LINKED)
    if position is not None:
        asyncio.run(_seed(storage.progression_repo, student.id, position))
    return student


def _card(api: TestClient, id: UUID) -> dict[str, Any]:
    response = api.get(CARD.format(id=id), headers=_auth())
    assert response.status_code == 200, response.text
    return response.json()


def _mark(api: TestClient, id: UUID, seen: Position, to: Position, user_id: int = ME_TG) -> Any:
    return api.post(MARK.format(id=id), json=_body(seen, to), headers=_auth(user_id))


# The card's next_asanas


def test_the_card_lists_the_next_three_stops_in_order(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me)

    body = _card(api, student.id)

    assert body["last_asana"] == _pos(KAPOTASANA_B)
    assert body["next_asanas"] == [
        _pos(SUPTA_VAJRASANA),
        _pos(BAKASANA_B),
        _pos(BHARADVAJASANA),
    ]


@pytest.mark.parametrize(
    ("position", "count"),
    [
        (Position("advanced-b", "urdhva-dandasana"), 2),
        (Position("advanced-b", "omkarasana"), 0),
        (None, 0),
    ],
    ids=["near-the-end", "the-end", "unset"],
)
def test_next_asanas_has_zero_to_three(
    api: TestClient, storage: InMemoryStorage, position: Position | None, count: int
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, position)

    assert len(_card(api, student.id)["next_asanas"]) == count


def test_next_asanas_is_in_the_openapi_card(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    card = spec["components"]["schemas"]["StudentCardOut"]

    assert card["properties"]["next_asanas"]["type"] == "array"


# POST new-asana


def test_marking_needs_auth(api: TestClient) -> None:
    response = api.post(MARK.format(id=uuid4()), json=_body(KAPOTASANA_B, SUPTA_VAJRASANA))

    assert (response.status_code, response.json()) == (401, {"code": "auth_missing"})


def test_a_mark_returns_the_refreshed_card_with_no_store(
    api: TestClient, storage: InMemoryStorage, notifier: FakeNotifier
) -> None:
    me = _me(api, storage)
    student = _student(storage, me)

    response = _mark(api, student.id, KAPOTASANA_B, BAKASANA_B)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body == _card(api, student.id)
    assert body["last_asana"] == _pos(BAKASANA_B)
    assert body["next_asanas"][0] == _pos(BHARADVAJASANA)
    [(recipient, teacher, mark)] = notifier.marked
    assert recipient == Recipient(str(STUDENT_TG), "ru")
    assert teacher == "Лена"
    assert mark.target == BAKASANA_B


def test_the_mark_lands_in_the_students_record_as_a_teachers(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me)

    _mark(api, student.id, KAPOTASANA_B, BHARADVAJASANA)

    state = storage.day_repo.progression_rows[student.id]
    assert state.position == BHARADVAJASANA
    assert state.items == ITEMS
    _, event = storage.day_repo.progression_events[-1]
    assert (event.kind, event.before, event.after) == (
        EventKind.GIVEN,
        KAPOTASANA_B,
        BHARADVAJASANA,
    )
    assert event.occurred_on == TODAY  # the student's (Almaty) today


def _unlinked(api: TestClient, storage: InMemoryStorage, me: UUID) -> UUID:
    stranger = add_person(storage.repo, "77", "Boris")
    storage.teacher_links.add(stranger.id, uuid4(), linked_on=LINKED)
    return stranger.id


def _reversed(api: TestClient, storage: InMemoryStorage, me: UUID) -> UUID:
    my_teacher = add_person(storage.repo, "78", "Dmitry")
    storage.teacher_links.add(me, my_teacher.id, linked_on=LINKED)
    return my_teacher.id


def _shala_student(api: TestClient, storage: InMemoryStorage, me: UUID) -> UUID:
    """Staff at the student's shala, with no link: no right to mark (ADR-0033)."""
    from tristhana.domain.shalas import ShalaRole

    student = add_person(storage.repo, "79", "Maria")
    shala = storage.shalas.add_shala(me, roles=frozenset({ShalaRole.TEACHER}))
    storage.shalas.add_student(shala.id, student.id)
    return student.id


def _unknown(api: TestClient, storage: InMemoryStorage, me: UUID) -> UUID:
    return uuid4()


@pytest.mark.parametrize(
    "who",
    [_unknown, _unlinked, _reversed, _shala_student],
    ids=["unknown", "unlinked", "reversed", "shala-staff"],
)
def test_one_404_for_anyone_not_on_the_list(
    api: TestClient, storage: InMemoryStorage, notifier: FakeNotifier, who: Any
) -> None:
    me = _me(api, storage)
    id = who(api, storage, me)

    response = _mark(api, id, KAPOTASANA_B, SUPTA_VAJRASANA)

    assert (response.status_code, response.json()) == (404, {"code": "not_linked"})
    assert notifier.marked == []


def test_from_other_than_the_current_position_is_409(
    api: TestClient, storage: InMemoryStorage, notifier: FakeNotifier
) -> None:
    """The student moved on after the card was read: refetch."""
    me = _me(api, storage)
    student = _student(storage, me, SUPTA_VAJRASANA)

    response = _mark(api, student.id, KAPOTASANA_B, BAKASANA_B)

    assert (response.status_code, response.json()) == (409, {"code": "progression_changed"})
    assert notifier.marked == []
    assert storage.day_repo.progression_rows[student.id].position == SUPTA_VAJRASANA


def test_a_retried_post_is_409(
    api: TestClient, storage: InMemoryStorage, notifier: FakeNotifier
) -> None:
    me = _me(api, storage)
    student = _student(storage, me)
    assert _mark(api, student.id, KAPOTASANA_B, SUPTA_VAJRASANA).status_code == 200

    again = _mark(api, student.id, KAPOTASANA_B, SUPTA_VAJRASANA)

    assert (again.status_code, again.json()) == (409, {"code": "progression_changed"})
    assert len(notifier.marked) == 1


@pytest.mark.parametrize(
    "to",
    [
        Position("intermediate", "ardha-matsyendrasana"),  # a 4th stop
        KAPOTASANA_B,  # the same
        Position("intermediate", "ustrasana"),  # back
        Position("intermediate", "kapotasana-a"),  # not a stop
        Position("advanced-c", "anything"),
    ],
    ids=["4th", "same", "back", "non-stop", "unconfirmed"],
)
def test_a_target_outside_the_next_three_of_from_is_422(
    api: TestClient, storage: InMemoryStorage, notifier: FakeNotifier, to: Position
) -> None:
    me = _me(api, storage)
    student = _student(storage, me)

    response = _mark(api, student.id, KAPOTASANA_B, to)

    assert (response.status_code, response.json()) == (422, {"code": "invalid_progression"})
    assert notifier.marked == []


def test_an_unset_student_is_409(api: TestClient, storage: InMemoryStorage) -> None:
    """The card has no `last_asana` to send; whatever `from` says, nothing is started."""
    me = _me(api, storage)
    student = _student(storage, me, None)
    first = Position("primary", "utthita-hasta-padangusthasana")

    response = _mark(api, student.id, Position(None, None), first)

    assert (response.status_code, response.json()) == (409, {"code": "progression_changed"})
    assert student.id not in storage.day_repo.progression_rows


def test_the_new_route_is_in_openapi(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    post = spec["paths"]["/api/v1/me/students/{id}/new-asana"]["post"]

    assert {"200", "404", "409", "422"} <= set(post["responses"])
    ref = post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    body = spec["components"]["schemas"][ref.rsplit("/", 1)[1]]
    assert set(body["properties"]) == {"from", "to"}


# The teacher's reply never varies with what they can't see


def _reply(
    held_before: bool, status: DeliveryStatus, with_change: bool, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, str]:
    storage = InMemoryStorage()
    repo = marking(storage)
    notifier = FakeNotifier(mark_outcomes=[DeliveryResult(status)])
    fixed = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: fixed)
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage, notifier)) as api:
        me = _me(api, storage)
        student = add_person(storage.repo, "2", "Anna", "en", "Asia/Almaty")
        storage.teacher_links.add(student.id, me, linked_on=LINKED)

        async def history() -> None:
            last = await _seed(repo, student.id, KAPOTASANA_B)
            if held_before:  # was at Bharadvajasana, changed back
                up = Change(
                    EventKind.CHANGED, TODAY, Progression(BHARADVAJASANA, ITEMS),
                    KAPOTASANA_B, BHARADVAJASANA,
                )  # fmt: skip
                moved = await repo.apply(student.id, up, last, student.id)
                assert moved is not None
                down = Change(
                    EventKind.CHANGED, TODAY, Progression(KAPOTASANA_B, ITEMS),
                    BHARADVAJASANA, KAPOTASANA_B,
                )  # fmt: skip
                assert await repo.apply(student.id, down, moved.id, student.id) is not None
            if with_change:
                state = storage.day_repo.progression_rows[student.id]
                more = ITEMS | {"standing-up"}
                item = Change(
                    EventKind.ITEM_GIVEN, TODAY, Progression(KAPOTASANA_B, more),
                    item="standing-up",
                )  # fmt: skip
                assert await repo.apply(student.id, item, state.last_event_id, student.id)

        asyncio.run(history())
        response = _mark(api, student.id, KAPOTASANA_B, SUPTA_VAJRASANA)
        return response.status_code, response.text.replace(str(student.id), "<id>")


def test_the_reply_is_byte_identical_whatever_the_history_or_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies = {
        _reply(held, status, change, monkeypatch)
        for held in (False, True)
        for status in (DeliveryStatus.SENT, DeliveryStatus.BLOCKED, DeliveryStatus.FAILED)
        for change in (False, True)
    }

    assert len(replies) == 1
    [(status, text)] = replies
    assert status == 200
    for hidden in ("event", "celebrat", "changed", "undo", "by_name", "drop-backs", "standing"):
        assert hidden not in text


def test_the_card_never_carries_events_or_celebrations(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me)
    _mark(api, student.id, KAPOTASANA_B, SUPTA_VAJRASANA)

    body = _card(api, student.id)

    assert set(body) == {"id", "name", "days", "last_asana", "next_asanas", "quiet"}


# The student's history: by, by_name, undoable, marked


def test_a_teachers_mark_reads_with_the_name_while_linked(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, telegram_id=STUDENT_TG, locale="en")
    _mark(api, student.id, KAPOTASANA_B, BHARADVAJASANA)

    body = api.get(MINE, headers=_auth(STUDENT_TG, "Anna")).json()

    newest, item, start = body["events"]
    assert (newest["kind"], newest["by"], newest["by_name"], newest["undoable"]) == (
        "given",
        "teacher",
        "Лена",
        True,
    )
    assert newest["marked_by_self"] is False
    assert (item["by"], item["by_name"], item["undoable"]) == ("self", None, False)
    assert (start["by"], start["undoable"]) == ("self", False)
    assert body["marked"] == {"event_id": newest["id"], "by_name": "Лена", "undoable": True}


def test_after_an_unlink_the_mark_reads_a_teacher_and_stays_undoable(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, locale="en")
    _mark(api, student.id, KAPOTASANA_B, SUPTA_VAJRASANA)
    storage.teacher_links.rows.pop((student.id, me))

    body = api.get(MINE, headers=_auth(STUDENT_TG, "Anna")).json()

    assert (body["events"][0]["by"], body["events"][0]["by_name"]) == ("teacher", None)
    assert body["marked"]["by_name"] is None
    assert body["marked"]["undoable"] is True


def test_the_students_own_history_has_no_mark(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    _student(storage, me, locale="en")

    body = api.get(MINE, headers=_auth(STUDENT_TG, "Anna")).json()

    assert body["marked"] is None
    assert [e["undoable"] for e in body["events"]] == [True, False]


def test_delete_of_a_retractable_non_latest_mark_is_200(
    api: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, locale="en")
    _mark(api, student.id, KAPOTASANA_B, BHARADVAJASANA)
    mark_id = storage.day_repo.progression_rows[student.id].last_event_id
    more = ITEMS | {"standing-up"}
    item = Change(
        EventKind.ITEM_GIVEN, TODAY, Progression(BHARADVAJASANA, more), item="standing-up"
    )
    assert asyncio.run(repo.apply(student.id, item, mark_id, student.id)) is not None
    student_auth = _auth(STUDENT_TG, "Anna")
    events = api.get(MINE, headers=student_auth).json()["events"]
    assert [e["undoable"] for e in events[:2]] == [True, True]

    response = api.delete(f"{MINE}/events/{mark_id}", headers=student_auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["position"] == _pos(KAPOTASANA_B)
    assert set(body["items"]) == more
    assert body["marked"] is None


def test_delete_of_a_mark_moved_on_from_is_409(
    api: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, locale="en")
    _mark(api, student.id, KAPOTASANA_B, SUPTA_VAJRASANA)
    mark_id = storage.day_repo.progression_rows[student.id].last_event_id
    student_auth = _auth(STUDENT_TG, "Anna")
    given = api.post(
        f"{MINE}/events",
        json={
            "kind": "given",
            "series": "intermediate",
            "last": "bakasana-b",
            "expected_event_id": mark_id,
        },
        headers=student_auth,
    )
    assert given.status_code == 201, given.text
    assert api.get(MINE, headers=student_auth).json()["events"][1]["undoable"] is False

    response = api.delete(f"{MINE}/events/{mark_id}", headers=student_auth)

    assert (response.status_code, response.json()) == (409, {"code": "not_latest"})


def test_the_event_fields_are_in_openapi(api: TestClient) -> None:
    schemas = api.get("/openapi.json").json()["components"]["schemas"]

    assert {"by", "by_name", "undoable"} <= set(schemas["EventOut"]["properties"])
    assert set(schemas["EventOut"]["properties"]["by"]["enum"]) == {"self", "teacher"}
    assert "marked" in schemas["ProgressionOut"]["properties"]


# Q159 (ST-04): the mark is found however many item events came after it


def test_a_mark_past_the_newest_20_events_stays_marked_and_undoable(
    api: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, locale="en")
    _mark(api, student.id, KAPOTASANA_B, BHARADVAJASANA)
    mark_id = storage.day_repo.progression_rows[student.id].last_event_id
    assert mark_id is not None
    last, items = mark_id, ITEMS
    for n in range(25):
        given = n % 2 == 0
        items = items | {"standing-up"} if given else items - {"standing-up"}
        kind = EventKind.ITEM_GIVEN if given else EventKind.ITEM_REMOVED
        change = Change(kind, TODAY, Progression(BHARADVAJASANA, items), item="standing-up")
        event = asyncio.run(repo.apply(student.id, change, last, student.id))
        assert event is not None
        last = event.id
    student_auth = _auth(STUDENT_TG, "Anna")

    body = api.get(MINE, headers=student_auth).json()

    assert len(body["events"]) == 20
    assert mark_id not in [e["id"] for e in body["events"]]
    assert body["marked"] == {"event_id": mark_id, "by_name": "Лена", "undoable": True}
    assert [e["undoable"] for e in body["events"]] == [True] + [False] * 19

    response = api.delete(f"{MINE}/events/{mark_id}", headers=student_auth)

    assert response.status_code == 200, response.text
    after = response.json()
    assert after["position"] == _pos(KAPOTASANA_B)
    assert set(after["items"]) == items
    assert after["marked"] is None
