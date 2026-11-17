"""Teacher-request endpoints (ID-07 spec §4, §8; ADR-0046): auth, the exact key sets, the
student's side with no state and no date (a quiet "no" serialises exactly as waiting), the
teacher's waiting list with `as_of`, approve / decline / reopen as 204, 404 `request_gone`
identical for every reason, 409 `list_full`, approve-all honouring `as_of`, ids that are no
capability, `no-store`, and the OpenAPI contract.

A waiting or declined request grants nothing a link grants: the student is absent from
`GET /me/students` and their card is 404 `not_linked`."""

import itertools
import json
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.shala_fakes import shala_storage
from tests.teacher_link_fakes import add_person
from tristhana.api.initdata import sign
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider
from tristhana.domain.shalas import ShalaRole
from tristhana.domain.teacher_links import MAX_TEACHERS
from tristhana.domain.teacher_requests import ANSWER_WITHIN, RequestState
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
LINKS = "/api/v1/me/links"
MINE = "/api/v1/me/teacher-requests"
THEIRS = "/api/v1/me/student-requests"
ALL = f"{THEIRS}/approve-all"
GONE = (404, {"code": "request_gone"})
A_WHILE = timedelta(hours=1)
_ids = itertools.count(270_000)


def _auth(user_id: int = ME_TG) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Ash", "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    """The app runs on the system clock, so the fakes' "database clock" is set to it: a
    row made here is a few microseconds old, as it would be in the database."""
    found = shala_storage()
    found.repo.clock.instant = datetime.now(UTC)
    return found


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(settings, storage)) as client:
        yield client


class World:
    """Me (Telegram 42) in a shala owned by someone else, as its teacher or as a student."""

    def __init__(self, api: TestClient, storage: InMemoryStorage) -> None:
        self.api = api
        self.storage = storage
        assert api.get("/api/v1/me", headers=_auth()).status_code == 200
        self.me: UUID = storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(ME_TG))]
        self.owner = self.person("Olga")
        self.shala: UUID = storage.shalas.add_shala(self.owner.id, roles=frozenset()).id
        self.joined = datetime.now(UTC) - timedelta(days=60)  # everyone joined long ago

    @property
    def requests(self) -> Any:
        return self.storage.teacher_requests

    def person(self, name: str | None = "Person") -> Account:
        return add_person(self.storage.repo, str(next(_ids)), name)

    def i_teach(self) -> None:
        self.storage.shalas.add_staff(self.shala, self.me, ShalaRole.TEACHER, at=self.joined)

    def i_study(self) -> None:
        self.storage.shalas.add_student(self.shala, self.me, at=self.joined)

    def teacher(self, name: str = "Anna") -> Account:
        found = self.person(name)
        self.storage.shalas.add_staff(self.shala, found.id, ShalaRole.TEACHER, at=self.joined)
        return found

    def student(self, name: str | None = "Boris") -> Account:
        found = self.person(name)
        self.storage.shalas.add_student(self.shala, found.id, at=self.joined)
        return found

    def asked(
        self,
        student: UUID,
        teacher: UUID,
        state: RequestState = RequestState.WAITING,
        ago: timedelta = A_WHILE,
        asked_on: date = date(2026, 11, 10),
        agreed: bool = True,
    ) -> Any:
        return self.requests.add(
            student,
            teacher,
            self.shala,
            state=state,
            asked_on=asked_on,
            agreed=agreed,
            created_at=datetime.now(UTC) - ago,
        )

    def state(self, student: UUID, teacher: UUID) -> RequestState | None:
        return self.requests.state_of(student, teacher)

    def get(self, url: str, **params: Any) -> Any:
        return self.api.get(url, headers=_auth(), params=params)

    def post(self, url: str, body: dict[str, Any] | None = None) -> Any:
        return self.api.post(url, headers=_auth(), json=body)

    def delete(self, url: str) -> Any:
        return self.api.delete(url, headers=_auth())

    def links(self) -> dict[str, Any]:
        response = self.get(LINKS)
        assert response.status_code == 200
        return response.json()

    def waiting(self, **params: Any) -> dict[str, Any]:
        response = self.get(THEIRS, **params)
        assert response.status_code == 200, response.text
        return response.json()

    def answer(self, action: str, student: UUID) -> tuple[int, Any]:
        response = self.post(f"{THEIRS}/{student}/{action}")
        return response.status_code, response.json() if response.content else None


@pytest.fixture
def world(api: TestClient, storage: InMemoryStorage) -> World:
    return World(api, storage)


ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("DELETE", f"{MINE}/{uuid4()}", None),
    ("GET", THEIRS, None),
    ("POST", f"{THEIRS}/{uuid4()}/approve", None),
    ("POST", f"{THEIRS}/{uuid4()}/decline", None),
    ("POST", f"{THEIRS}/{uuid4()}/reopen", None),
    ("POST", ALL, {"as_of": "2026-11-17T10:30:00Z"}),
]


@pytest.mark.parametrize(("method", "url", "body"), ROUTES)
def test_every_route_needs_auth(
    api: TestClient, method: str, url: str, body: dict[str, Any] | None
) -> None:
    response = api.request(method, url, json=body)

    assert (response.status_code, response.json()) == (401, {"code": "auth_missing"})


# The student's side: `GET /me/links` and the withdrawal


def test_links_of_someone_new_hold_no_request(world: World) -> None:
    assert world.links() == {"teachers": [], "students": [], "asked": [], "waiting": 0}


def test_the_students_waiting_line_has_exactly_the_agreed_keys(world: World) -> None:
    world.i_study()
    anna = world.teacher("Анна")
    world.asked(world.me, anna.id)

    body = world.links()

    assert set(body) == {"teachers", "students", "asked", "waiting"}
    [line] = body["asked"]
    assert set(line) == {"teacher_id", "name", "shala"}  # no state, no date
    assert set(line["shala"]) == {"id", "name"}
    assert line == {
        "teacher_id": str(anna.id),
        "name": "Анна",
        "shala": {"id": str(world.shala), "name": "Ashtanga Almaty"},
    }
    assert body["teachers"] == []  # a request is not a link
    assert body["waiting"] == 0  # nobody waits for me


def test_a_quiet_no_serialises_exactly_as_waiting_for_the_student(world: World) -> None:
    world.i_study()
    anna, boris = world.teacher("Anna"), world.teacher("Boris")
    world.asked(world.me, anna.id, ago=timedelta(days=2))
    row = world.asked(world.me, boris.id, ago=timedelta(days=1))

    waiting = world.get(LINKS)
    row.state = RequestState.DECLINED
    declined = world.get(LINKS)

    assert declined.status_code == waiting.status_code == 200
    assert declined.content == waiting.content  # byte for byte
    assert [line["name"] for line in waiting.json()["asked"]] == ["Anna", "Boris"]  # oldest first
    for word in ("declin", "state", "created", "asked_on", "status"):
        assert word not in declined.text, word


@pytest.mark.parametrize("state", [RequestState.WAITING, RequestState.DECLINED])
def test_after_seven_days_the_line_is_gone_either_way(world: World, state: RequestState) -> None:
    world.i_study()
    anna = world.teacher()
    world.asked(world.me, anna.id, state, ago=ANSWER_WITHIN + A_WHILE)

    assert world.links()["asked"] == []


@pytest.mark.parametrize("state", [RequestState.WITHDRAWN, RequestState.APPROVED])
def test_a_closed_request_is_no_waiting_line(world: World, state: RequestState) -> None:
    world.i_study()
    anna = world.teacher()
    world.asked(world.me, anna.id, state)

    assert world.links()["asked"] == []


def test_links_count_who_waits_for_my_answer(world: World) -> None:
    world.i_teach()
    for name, state in (("A", "waiting"), ("B", "waiting"), ("C", "declined"), ("D", "withdrawn")):
        world.asked(world.student(name).id, world.me, RequestState(state))

    body = world.links()

    assert body["waiting"] == 2  # not answered yet: a "no" and a withdrawal don't wait
    assert body["asked"] == []
    assert body["students"] == []  # nobody is a student before the yes


def test_the_main_teacher_answer_carries_the_requests_too(world: World) -> None:
    world.i_study()
    linked, asked = world.teacher("Linked"), world.teacher("Asked")
    world.storage.teacher_links.add(world.me, linked.id)
    world.asked(world.me, asked.id)

    response = world.api.put(f"/api/v1/me/teachers/{linked.id}/primary", headers=_auth())

    assert response.status_code == 200
    assert response.json() == world.links()
    assert [line["name"] for line in response.json()["asked"]] == ["Asked"]


@pytest.mark.parametrize("state", [RequestState.WAITING, RequestState.DECLINED])
def test_withdraw_is_204_twice_and_looks_the_same_after_a_quiet_no(
    world: World, state: RequestState
) -> None:
    world.i_study()
    anna = world.teacher()
    world.asked(world.me, anna.id, state)

    first = world.delete(f"{MINE}/{anna.id}")
    second = world.delete(f"{MINE}/{anna.id}")

    assert (first.status_code, first.content) == (204, b"")
    assert (second.status_code, second.content) == (204, b"")
    assert world.state(world.me, anna.id) is RequestState.WITHDRAWN
    assert world.links()["asked"] == []


def test_withdraw_after_the_yes_is_204_and_removes_no_link(world: World) -> None:
    world.i_study()
    anna = world.teacher()
    world.asked(world.me, anna.id, RequestState.APPROVED)
    world.storage.teacher_links.add(world.me, anna.id)

    response = world.delete(f"{MINE}/{anna.id}")

    assert response.status_code == 204
    assert world.storage.teacher_links.teachers_of(world.me) == [anna.id]
    assert world.state(world.me, anna.id) is RequestState.APPROVED


def test_withdraw_touches_only_my_own_request(world: World) -> None:
    anna, other = world.teacher(), world.student()
    world.asked(other.id, anna.id)

    by_teacher = world.delete(f"{MINE}/{anna.id}")  # I never asked Anna
    by_student = world.delete(f"{MINE}/{other.id}")  # an id from someone else's row
    unknown = world.delete(f"{MINE}/{uuid4()}")

    assert {r.status_code for r in (by_teacher, by_student, unknown)} == {204}
    assert world.state(other.id, anna.id) is RequestState.WAITING


# The teacher's side: the waiting list


def test_the_waiting_list_has_exactly_the_agreed_keys(world: World) -> None:
    world.i_teach()
    boris = world.student("Boris")
    world.asked(boris.id, world.me)

    body = world.waiting()

    assert set(body) == {"requests", "total", "as_of"}
    [line] = body["requests"]
    assert set(line) == {"student_id", "name", "shala"}
    assert line == {
        "student_id": str(boris.id),
        "name": "Boris",
        "shala": {"id": str(world.shala), "name": "Ashtanga Almaty"},
    }
    assert body["total"] == 1
    as_of = datetime.fromisoformat(body["as_of"])
    assert as_of.tzinfo is not None
    assert abs(datetime.now(UTC) - as_of) < timedelta(minutes=5)


def test_someone_nobody_asked_gets_an_empty_list(world: World) -> None:
    body = world.waiting()

    assert (body["requests"], body["total"]) == ([], 0)


def test_the_waiting_list_pages_oldest_first_with_the_full_total(world: World) -> None:
    world.i_teach()
    for i in range(5):
        world.asked(world.student(f"S{i}").id, world.me, ago=timedelta(hours=10 - i))
    world.asked(world.student("No").id, world.me, RequestState.DECLINED)
    world.asked(world.student("Old").id, world.me, ago=ANSWER_WITHIN + A_WHILE)

    first, second = world.waiting(limit=2), world.waiting(offset=4, limit=2)

    assert [r["name"] for r in first["requests"]] == ["S0", "S1"]
    assert [r["name"] for r in second["requests"]] == ["S4"]
    assert (first["total"], second["total"]) == (5, 5)
    assert [r["name"] for r in world.waiting()["requests"]] == ["S0", "S1", "S2", "S3", "S4"]


@pytest.mark.parametrize("params", [{"limit": 51}, {"limit": 0}, {"offset": -1}])
def test_paging_out_of_bounds_is_a_validation_error(world: World, params: dict[str, int]) -> None:
    assert world.get(THEIRS, **params).status_code == 422


def test_fifty_a_page_is_allowed(world: World) -> None:
    assert world.get(THEIRS, limit=50).status_code == 200


def test_only_the_asked_teacher_sees_a_request(world: World) -> None:
    """Not the owner, a manager or another teacher (Q322): the list is keyed on the caller."""
    world.i_teach()
    anna = world.teacher("Anna")
    world.asked(world.student().id, anna.id)

    assert world.waiting()["requests"] == []
    assert world.links()["waiting"] == 0


# Yes, no, undo


def test_approve_is_204_and_makes_the_link_from_the_day_the_student_asked(world: World) -> None:
    world.i_teach()
    boris = world.student("Boris")
    world.asked(boris.id, world.me, asked_on=date(2026, 11, 10))

    response = world.post(f"{THEIRS}/{boris.id}/approve")

    assert (response.status_code, response.content) == (204, b"")
    assert world.state(boris.id, world.me) is RequestState.APPROVED
    link = world.storage.teacher_links.rows[(boris.id, world.me)]
    assert (link.linked_on, link.is_primary) == (date(2026, 11, 10), False)
    assert [s["id"] for s in world.links()["students"]] == [str(boris.id)]
    assert world.waiting()["total"] == 0


@pytest.mark.parametrize("agreed", [True, False])
def test_approve_copies_the_quiet_note_consent_and_never_sets_it(
    world: World, agreed: bool
) -> None:
    """The flag is what the student's tap agreed to (ADR-0031): the teacher's yes carries no
    consent of its own."""
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me, agreed=agreed)

    assert world.answer("approve", boris.id) == (204, None)
    assert world.storage.teacher_links.rows[(boris.id, world.me)].quiet_note_agreed is agreed


def test_approve_twice_is_204_and_one_link(world: World) -> None:
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me)

    answers = [world.answer("approve", boris.id) for _ in range(2)]

    assert answers == [(204, None), (204, None)]
    assert world.storage.teacher_links.students_of(world.me) == [boris.id]


def test_a_quiet_no_can_still_become_a_yes(world: World) -> None:
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me, RequestState.DECLINED)

    assert world.answer("approve", boris.id) == (204, None)
    assert (boris.id, world.me) in world.storage.teacher_links.rows


def test_decline_is_idempotent_and_changes_nothing_the_student_sees(
    world: World, storage: InMemoryStorage
) -> None:
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me)
    before = storage.teacher_requests.rows[(boris.id, world.me)].created_at

    answers = [world.answer("decline", boris.id) for _ in range(2)]

    assert answers == [(204, None), (204, None)]
    assert world.state(boris.id, world.me) is RequestState.DECLINED
    assert world.waiting()["requests"] == []
    after = storage.teacher_requests.rows[(boris.id, world.me)].created_at
    assert after == before  # a "no" moves no clock
    assert storage.teacher_links.rows == {}


def test_reopen_brings_a_declined_request_back(world: World) -> None:
    world.i_teach()
    boris = world.student("Boris")
    world.asked(boris.id, world.me, RequestState.DECLINED)

    answers = [world.answer("reopen", boris.id) for _ in range(2)]

    assert answers == [(204, None), (204, None)]
    assert world.state(boris.id, world.me) is RequestState.WAITING
    assert [r["name"] for r in world.waiting()["requests"]] == ["Boris"]


def _gone_cases() -> list[str]:
    return ["unknown", "expired", "withdrawn", "left", "role", "became_staff", "approved_unlinked"]


def _make_gone(world: World, reason: str) -> UUID:
    """A request that can no longer be answered, for each reason the spec lists."""
    shalas = world.storage.shalas
    if reason == "unknown":
        return uuid4()
    boris = world.student()
    if reason == "expired":
        world.asked(boris.id, world.me, ago=ANSWER_WITHIN + A_WHILE)
    elif reason == "withdrawn":
        world.asked(boris.id, world.me, RequestState.WITHDRAWN)
    elif reason == "approved_unlinked":  # confirmed once; the link is no longer there
        world.asked(boris.id, world.me, RequestState.APPROVED, ago=timedelta(days=3))
    else:
        world.asked(boris.id, world.me)
        if reason == "left":
            del shalas.students_rows[(world.shala, boris.id)]
        elif reason == "role":
            shalas.staff[(world.shala, world.me)].roles = frozenset({ShalaRole.ASSISTANT})
        elif reason == "became_staff":
            shalas.add_staff(world.shala, boris.id, ShalaRole.ASSISTANT)
    return boris.id


@pytest.mark.parametrize("action", ["approve", "decline", "reopen"])
@pytest.mark.parametrize("reason", _gone_cases())
def test_gone_is_one_answer_for_every_reason(world: World, action: str, reason: str) -> None:
    world.i_teach()
    student = _make_gone(world, reason)

    response = world.post(f"{THEIRS}/{student}/{action}")

    assert (response.status_code, response.content) == (404, b'{"code":"request_gone"}')
    assert response.headers["cache-control"] == "no-store"
    assert world.storage.teacher_links.rows == {}


def test_a_full_list_is_409_and_the_request_stays(world: World) -> None:
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me)
    for _ in range(MAX_TEACHERS):  # the student's own list of teachers is full
        world.storage.teacher_links.add(boris.id, world.person("T").id)

    answer = world.answer("approve", boris.id)

    assert answer == (409, {"code": "list_full"})
    assert world.state(boris.id, world.me) is RequestState.WAITING
    assert (boris.id, world.me) not in world.storage.teacher_links.rows
    assert world.waiting()["total"] == 1


@pytest.mark.parametrize("action", ["decline", "reopen"])
def test_a_no_never_removes_a_link(world: World, action: str) -> None:
    """Linked meanwhile (the personal link, or a yes from another device): there is no
    request left to answer, and the student stays on the list."""
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me)
    world.storage.teacher_links.add(boris.id, world.me)

    assert world.answer(action, boris.id) == GONE
    assert world.storage.teacher_links.students_of(world.me) == [boris.id]
    assert world.state(boris.id, world.me) is RequestState.WAITING


def test_a_yes_on_someone_already_linked_is_204(world: World) -> None:
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me)
    world.storage.teacher_links.add(boris.id, world.me)

    assert world.answer("approve", boris.id) == (204, None)
    assert world.storage.teacher_links.students_of(world.me) == [boris.id]


@pytest.mark.parametrize("action", ["approve", "decline", "reopen"])
def test_an_id_from_someone_elses_request_touches_nothing(world: World, action: str) -> None:
    """An id is no capability: every write is keyed on the caller. The owner can't answer
    for a teacher either."""
    world.i_teach()
    anna, boris = world.teacher("Anna"), world.student()
    state = RequestState.DECLINED if action == "reopen" else RequestState.WAITING
    world.asked(boris.id, anna.id, state)

    assert world.answer(action, boris.id) == GONE
    assert world.answer(action, anna.id) == GONE
    assert world.state(boris.id, anna.id) is state
    assert world.storage.teacher_links.rows == {}


@pytest.mark.parametrize(
    "url",
    [f"{MINE}/nope", f"{THEIRS}/nope/approve", f"{THEIRS}/nope/decline", f"{THEIRS}/nope/reopen"],
)
def test_a_malformed_id_is_a_validation_error(world: World, url: str) -> None:
    method = "DELETE" if url.startswith(MINE) else "POST"

    assert world.api.request(method, url, headers=_auth()).status_code == 422


# Confirm all


def test_approve_all_honours_as_of(world: World) -> None:
    world.i_teach()
    seen = [world.student(f"S{i}") for i in range(3)]
    for i, student in enumerate(seen):
        world.asked(student.id, world.me, ago=timedelta(hours=5 - i))
    quiet_no = world.student("No")
    world.asked(quiet_no.id, world.me, RequestState.DECLINED, ago=timedelta(hours=6))
    listed = world.waiting()
    late = world.student("Late")  # asks after the list was drawn
    world.requests.add(late.id, world.me, world.shala)

    response = world.post(ALL, {"as_of": listed["as_of"]})  # sent back unchanged

    assert response.status_code == 200
    assert response.json() == {"approved": 3, "left": 1}
    assert set(response.json()) == {"approved", "left"}
    assert world.storage.teacher_links.students_of(world.me) == [s.id for s in seen]
    assert world.state(late.id, world.me) is RequestState.WAITING  # never confirmed unseen
    assert world.state(quiet_no.id, world.me) is RequestState.DECLINED  # never a declined one
    assert [r["name"] for r in world.waiting()["requests"]] == ["Late"]


def test_approve_all_with_an_old_moment_confirms_nobody(world: World) -> None:
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me)
    long_ago = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    response = world.post(ALL, {"as_of": long_ago})

    assert response.json() == {"approved": 0, "left": 1}
    assert world.state(boris.id, world.me) is RequestState.WAITING


def test_approve_all_confirms_only_my_own_list(world: World) -> None:
    world.i_teach()
    anna, boris = world.teacher("Anna"), world.student()
    world.asked(boris.id, anna.id)

    response = world.post(ALL, {"as_of": world.waiting()["as_of"]})

    assert response.json() == {"approved": 0, "left": 0}
    assert world.state(boris.id, anna.id) is RequestState.WAITING


def test_approve_all_stops_at_a_full_list(world: World) -> None:
    world.i_teach()
    full, free = world.student("Full"), world.student("Free")
    world.asked(full.id, world.me, ago=timedelta(hours=3))
    world.asked(free.id, world.me, ago=timedelta(hours=2))
    for _ in range(MAX_TEACHERS):
        world.storage.teacher_links.add(full.id, world.person("T").id)

    response = world.post(ALL, {"as_of": world.waiting()["as_of"]})

    assert response.json() == {"approved": 1, "left": 1}
    assert world.state(full.id, world.me) is RequestState.WAITING


@pytest.mark.parametrize(
    "body",
    [None, {}, {"as_of": None}, {"as_of": "yesterday"}, {"as_of": "2026-11-17T10:30:00"}],
)
def test_approve_all_needs_a_moment_with_a_zone(world: World, body: dict[str, Any] | None) -> None:
    world.i_teach()
    boris = world.student()
    world.asked(boris.id, world.me)

    assert world.post(ALL, body).status_code == 422
    assert world.state(boris.id, world.me) is RequestState.WAITING


# A request is not a link


@pytest.mark.parametrize("state", [RequestState.WAITING, RequestState.DECLINED])
def test_a_waiting_or_declined_request_grants_nothing(world: World, state: RequestState) -> None:
    world.i_teach()
    boris = world.student("Boris")
    world.asked(boris.id, world.me, state)

    students = world.get("/api/v1/me/students")
    card = world.get(f"/api/v1/me/students/{boris.id}")
    mark = world.post(
        f"/api/v1/me/students/{boris.id}/new-asana",
        {
            "from": {"series": "intermediate", "last": "kapotasana-b"},
            "to": {"series": "intermediate", "last": "supta-vajrasana"},
        },
    )

    assert students.json() == {"students": [], "total": 0}
    assert (card.status_code, card.json()) == (404, {"code": "not_linked"})
    assert (mark.status_code, mark.json()) == (404, {"code": "not_linked"})
    assert "Boris" not in students.text + card.text + mark.text
    assert world.links()["students"] == []


def test_the_student_reads_nothing_of_the_teacher_before_the_yes(world: World) -> None:
    world.i_study()
    anna = world.teacher("Anna")
    world.asked(world.me, anna.id)

    body = world.links()

    assert body["teachers"] == []
    assert world.api.put(f"/api/v1/me/teachers/{anna.id}/primary", headers=_auth()).json() == {
        "code": "not_linked"
    }


# Headers and the contract


def test_every_answer_is_no_store(world: World) -> None:
    world.i_teach()
    a, b, c = (world.student(n) for n in "ABC")
    for student in (a, b, c):
        world.asked(student.id, world.me)
    listed = world.get(THEIRS)

    answers = [
        world.get(LINKS),
        listed,
        world.post(f"{THEIRS}/{a.id}/approve"),
        world.post(f"{THEIRS}/{b.id}/decline"),
        world.post(f"{THEIRS}/{b.id}/reopen"),
        world.post(ALL, {"as_of": listed.json()["as_of"]}),
        world.delete(f"{MINE}/{uuid4()}"),
    ]

    for answer in answers:
        assert answer.is_success, answer.request.url
        assert answer.headers["cache-control"] == "no-store", answer.request.url


def _schema(api: TestClient) -> dict[str, Any]:
    return api.get("/openapi.json").json()


def _properties(schema: dict[str, Any], name: str) -> set[str]:
    return set(schema["components"]["schemas"][name]["properties"])


def test_openapi_lists_the_error_codes(api: TestClient) -> None:
    codes = _schema(api)["components"]["schemas"]["ErrorCode"]["enum"]

    assert {"request_gone", "list_full"} <= set(codes)


def test_no_student_facing_schema_has_a_state_or_a_date(api: TestClient) -> None:
    schema = _schema(api)

    assert _properties(schema, "AskedTeacherOut") == {"teacher_id", "name", "shala"}
    assert _properties(schema, "RequestShalaOut") == {"id", "name"}
    assert _properties(schema, "LinksOut") == {"teachers", "students", "asked", "waiting"}
    asked = json.dumps(schema["components"]["schemas"]["AskedTeacherOut"]).lower()
    for word in ("state", "date", "declin", "created", "asked_on"):
        assert word not in asked, word


def test_the_teachers_schemas_are_the_agreed_ones(api: TestClient) -> None:
    schema = _schema(api)

    assert _properties(schema, "StudentRequestOut") == {"student_id", "name", "shala"}
    assert _properties(schema, "StudentRequestsOut") == {"requests", "total", "as_of"}
    assert _properties(schema, "ApproveAllIn") == {"as_of"}
    assert _properties(schema, "ApprovedAllOut") == {"approved", "left"}


def test_no_request_schema_could_carry_a_no(api: TestClient) -> None:
    """The teacher's own action has a route and nothing else: no field, enum or description
    of these schemas holds a state."""
    schemas = _schema(api)["components"]["schemas"]
    ours = (
        "LinksOut",
        "AskedTeacherOut",
        "RequestShalaOut",
        "StudentRequestOut",
        "StudentRequestsOut",
        "ApproveAllIn",
        "ApprovedAllOut",
    )

    for name in ours:
        text = json.dumps(schemas[name]).lower()
        assert "declin" not in text, name
        assert "state" not in text, name


def test_the_routes_and_their_errors_are_in_the_contract(api: TestClient) -> None:
    paths = _schema(api)["paths"]

    assert set(paths[f"{MINE}/{{teacher_id}}"]) == {"delete"}
    assert set(paths[THEIRS]) == {"get"}
    assert set(paths[ALL]) == {"post"}
    approve = paths[f"{THEIRS}/{{student_id}}/approve"]["post"]["responses"]
    assert {"204", "404", "409"} <= set(approve)
    for action in ("decline", "reopen"):
        responses = paths[f"{THEIRS}/{{student_id}}/{action}"]["post"]["responses"]
        assert {"204", "404"} <= set(responses)
        assert "409" not in responses
    # No ask route yet (§2): the consent text lives in one place, the bot.
    assert not any(p.startswith(MINE) and "post" in ops for p, ops in paths.items())


def test_the_mini_apps_contract_has_the_routes() -> None:
    """The TS client is generated from this file: `npm run typecheck` builds against it."""
    path = Path(__file__).resolve().parents[3] / "miniapp" / "src" / "api" / "openapi.json"
    contract = json.loads(path.read_text())

    assert {
        f"{MINE}/{{teacher_id}}",
        THEIRS,
        ALL,
        f"{THEIRS}/{{student_id}}/approve",
        f"{THEIRS}/{{student_id}}/decline",
        f"{THEIRS}/{{student_id}}/reopen",
    } <= contract["paths"].keys()
    links = contract["components"]["schemas"]["LinksOut"]
    assert {"asked", "waiting"} <= set(links["properties"])
    codes = contract["components"]["schemas"]["ErrorCode"]["enum"]
    assert {"request_gone", "list_full"} <= set(codes)
