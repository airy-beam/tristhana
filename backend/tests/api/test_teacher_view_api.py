"""The teacher view's endpoints (ST-06, spec §4, §8): the exact response shapes, recursively and
in OpenAPI; the list carries no date, `days`, `quiet` or `last_asana`; the flag is nowhere; two
states plus null; one 404 for unknown, unlinked and reverse ids; paging limits and `no-store`.
Real use cases over the in-memory port, with a frozen clock."""

import json
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FixedClock, InMemoryStorage
from tests.teacher_link_fakes import add_person
from tristhana.api.initdata import sign
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.practice import Practice, PracticeLength
from tristhana.domain.progression import STANDING_ONLY, Position, Progression
from tristhana.domain.rest_periods import RestPeriod
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ME_TG = 42
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
TODAY = date(2026, 11, 7)
LINKED = date(2026, 6, 1)
STUDENTS = "/api/v1/me/students"
CARD = "/api/v1/me/students/{id}"
LENGTH = PracticeLength(("primary",), "navasana", None)


def _ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def _auth(user_id: int = ME_TG) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Ash", "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    fixed = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: fixed)
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage, user_id: int = ME_TG) -> UUID:
    assert api.get("/api/v1/me", headers=_auth(user_id)).status_code == 200
    return storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(user_id))]


def _student(
    storage: InMemoryStorage,
    me: UUID,
    telegram_id: str = "2",
    name: str | None = "Anna",
    agreed: bool = True,
    linked_on: date = LINKED,
) -> Account:
    student = add_person(storage.repo, telegram_id, name, "en", "UTC")
    storage.teacher_links.add(student.id, me, linked_on=linked_on, quiet_note_agreed=agreed)
    return student


def _log(storage: InMemoryStorage, who: Account, day: date, status: DayStatus) -> None:
    storage.day_repo.rows[(who.id, day)] = (DayLog(day, status), "UTC")


def _practiced(storage: InMemoryStorage, who: Account, day: date) -> None:
    _log(storage, who, day, DayStatus.PRACTICED)
    storage.day_repo.practice_rows[(who.id, day)] = Practice(length=LENGTH)


def _get(api: TestClient, path: str) -> dict[str, Any]:
    response = api.get(path, headers=_auth())
    assert response.status_code == 200, response.text
    return response.json()


def _card(api: TestClient, id: UUID) -> dict[str, Any]:
    return _get(api, CARD.format(id=id))


def _keys(value: Any, path: str = "") -> set[str]:
    """Every key path of a JSON value; list items share one path."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, inner in cast(dict[str, Any], value).items():
            found.add(f"{path}{key}")
            found |= _keys(inner, f"{path}{key}.")
    elif isinstance(value, list):
        for inner in cast(list[Any], value):
            found |= _keys(inner, path)
    return found


@pytest.mark.parametrize(("url"), [STUDENTS, CARD.format(id=uuid4())])
def test_both_reads_need_auth(api: TestClient, url: str) -> None:
    response = api.get(url)

    assert (response.status_code, response.json()) == (401, {"code": "auth_missing"})


# The list


def test_the_list_is_id_name_and_todays_state_and_nothing_else(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    anna = _student(storage, me, "2", "Anna")
    boris = _student(storage, me, "3", "Boris")
    clara = _student(storage, me, "4", None)
    _practiced(storage, anna, TODAY)
    _log(storage, boris, TODAY, DayStatus.LADIES)

    body = _get(api, STUDENTS)

    assert body == {
        "students": [
            {"id": str(anna.id), "name": "Anna", "today": "practiced"},
            {"id": str(boris.id), "name": "Boris", "today": "rest"},
            {"id": str(clara.id), "name": None, "today": None},
        ],
        "total": 3,
    }


def test_list_item_keys_exclude_any_date_days_quiet_or_last_asana(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, agreed=True)  # 21 blank days: the card's note is in play
    storage.day_repo.progression_rows[student.id] = Progression(Position("primary", "navasana"))

    response = api.get(STUDENTS, headers=_auth())

    assert _keys(response.json()) == {
        "students",
        "students.id",
        "students.name",
        "students.today",
        "total",
    }
    assert TODAY.isoformat() not in response.text
    assert "quiet" not in response.text


def test_a_0_student_account_gets_200_and_an_empty_list(
    api: TestClient, storage: InMemoryStorage
) -> None:
    _me(api, storage)

    assert _get(api, STUDENTS) == {"students": [], "total": 0}


def test_only_ones_own_students_are_listed(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    other_teacher = add_person(storage.repo, "9", "Boris")
    mine = _student(storage, me, "2")
    _student(storage, other_teacher.id, "3", "Theirs")

    assert [s["id"] for s in _get(api, STUDENTS)["students"]] == [str(mine.id)]


def test_the_default_page_is_20_and_a_limit_of_50_is_allowed(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    for n in range(25):
        _student(storage, me, f"{100 + n}", f"S{n:02d}")

    first = _get(api, STUDENTS)
    wide = _get(api, f"{STUDENTS}?limit=50")

    assert (len(first["students"]), first["total"]) == (20, 25)
    assert (len(wide["students"]), wide["total"]) == (25, 25)


def test_offset_and_limit_page_the_list(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    for n in range(5):
        _student(storage, me, f"{100 + n}", f"S{n}")

    body = _get(api, f"{STUDENTS}?offset=3&limit=1")

    assert [s["name"] for s in body["students"]] == ["S3"]
    assert body["total"] == 5


def test_an_offset_past_the_end_returns_empty_with_total_0(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    _student(storage, me)

    assert _get(api, f"{STUDENTS}?offset=40") == {"students": [], "total": 0}


def test_a_limit_over_50_is_422(api: TestClient) -> None:
    assert api.get(f"{STUDENTS}?limit=51", headers=_auth()).status_code == 422


def test_an_offset_past_any_possible_list_is_422_before_the_database(api: TestClient) -> None:
    """A huge offset once reached Postgres as an out-of-range bigint (ST-06 review)."""
    assert api.get(f"{STUDENTS}?offset={10**20}", headers=_auth()).status_code == 422
    assert api.get(f"{STUDENTS}?offset=501", headers=_auth()).status_code == 422


# The card


def test_the_card_has_the_exact_shape(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    student = _student(storage, me)
    _practiced(storage, student, TODAY)
    _log(storage, student, _ago(1), DayStatus.SICK)
    storage.day_repo.progression_rows[student.id] = Progression(Position("primary", "navasana"))

    body = _card(api, student.id)

    blank = [{"date": _ago(n).isoformat(), "state": None, "length": None} for n in range(6, 1, -1)]
    assert body == {
        "id": str(student.id),
        "name": "Anna",
        "days": [
            *blank,
            {"date": _ago(1).isoformat(), "state": "rest", "length": None},
            {
                "date": TODAY.isoformat(),
                "state": "practiced",
                "length": {"series": ["primary"], "end": "navasana", "first_part": None},
            },
        ],
        "last_asana": {"series": "primary", "last": "navasana"},
        # PR-08 Phase 3: the next three stops, from the shown position only.
        "next_asanas": [
            {"series": "primary", "last": "bhujapidasana"},
            {"series": "primary", "last": "kurmasana"},
            {"series": "primary", "last": "supta-kurmasana"},
        ],
        "quiet": False,
    }


def test_the_card_keys_are_exact_all_the_way_down(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me)
    _practiced(storage, student, TODAY)
    storage.day_repo.progression_rows[student.id] = Progression(Position("primary", "navasana"))

    assert _keys(_card(api, student.id)) == {
        "id",
        "name",
        "days",
        "days.date",
        "days.state",
        "days.length",
        "days.length.series",
        "days.length.end",
        "days.length.first_part",
        "last_asana",
        "last_asana.series",
        "last_asana.last",
        "next_asanas",
        "next_asanas.series",
        "next_asanas.last",
        "quiet",
    }


def test_last_asana_null_is_not_set_and_nulls_inside_are_standing_only(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    unset, standing = _student(storage, me, "2"), _student(storage, me, "3")
    storage.day_repo.progression_rows[standing.id] = Progression(STANDING_ONLY)

    assert _card(api, unset.id)["last_asana"] is None
    assert _card(api, standing.id)["last_asana"] == {"series": None, "last": None}


@pytest.mark.parametrize(
    "status",
    [DayStatus.REST, DayStatus.MOON, DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL],
    ids=lambda s: s.value,
)
def test_every_rest_kind_answers_the_same_bytes(
    api: TestClient, storage: InMemoryStorage, status: DayStatus
) -> None:
    me = _me(api, storage)
    plain, kind = _student(storage, me, "2"), _student(storage, me, "3")
    _log(storage, plain, TODAY, DayStatus.REST)
    _log(storage, kind, TODAY, status)

    first = api.get(CARD.format(id=plain.id), headers=_auth()).text
    second = api.get(CARD.format(id=kind.id), headers=_auth()).text

    assert second.replace(str(kind.id), str(plain.id)) == first


def test_no_practice_and_unlogged_answer_the_same_bytes_with_the_note_in_play(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    tapped, silent = _student(storage, me, "2"), _student(storage, me, "3")
    for n in range(21):
        _log(storage, tapped, _ago(n), DayStatus.SKIPPED)

    first = api.get(CARD.format(id=tapped.id), headers=_auth())
    second = api.get(CARD.format(id=silent.id), headers=_auth())

    assert first.json()["quiet"] is True
    assert first.text.replace(str(tapped.id), str(silent.id)) == second.text


def test_a_period_shows_up_to_today_and_no_further(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me)
    storage.day_repo.periods.rows[(student.id, _ago(1))] = RestPeriod(
        _ago(1), TODAY + timedelta(days=4), DayStatus.LADIES
    )

    days = _card(api, student.id)["days"]

    assert [d["state"] for d in days[-2:]] == ["rest", "rest"]
    assert days[-1]["date"] == TODAY.isoformat()


@pytest.mark.parametrize("agreed", [True, False])
def test_the_flag_only_ever_shows_as_the_note(
    api: TestClient, storage: InMemoryStorage, agreed: bool
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, agreed=agreed)

    response = api.get(CARD.format(id=student.id), headers=_auth())

    assert response.json()["quiet"] is agreed
    assert "quiet_note_agreed" not in response.text
    assert "agreed" not in response.text


def test_nothing_of_the_zone_or_the_link_date_is_returned(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _student(storage, me, linked_on=date(2026, 2, 3))

    for url in (STUDENTS, CARD.format(id=student.id)):
        text = api.get(url, headers=_auth()).text
        assert "2026-02-03" not in text
        assert "UTC" not in text
        assert "timezone" not in text


# One 404


def test_unknown_unlinked_and_reverse_ids_give_the_same_404_body(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    stranger = add_person(storage.repo, "9", "Mallory")
    my_teacher = add_person(storage.repo, "8", "Лена")
    storage.teacher_links.add(me, my_teacher.id)

    answers = [
        api.get(CARD.format(id=id), headers=_auth()) for id in (uuid4(), stranger.id, my_teacher.id)
    ]

    assert {a.status_code for a in answers} == {404}
    assert {a.text for a in answers} == {'{"code":"not_linked"}'}


def test_a_removed_student_is_404_at_once(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    student = _student(storage, me)
    assert api.delete(CARD.format(id=student.id), headers=_auth()).status_code == 204

    assert api.get(CARD.format(id=student.id), headers=_auth()).status_code == 404
    assert _get(api, STUDENTS) == {"students": [], "total": 0}


def test_a_malformed_id_is_a_validation_error(api: TestClient) -> None:
    assert api.get(CARD.format(id="not-a-uuid"), headers=_auth()).status_code == 422


def test_both_answers_are_no_store(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    student = _student(storage, me)

    for url in (STUDENTS, CARD.format(id=student.id)):
        response = api.get(url, headers=_auth())
        assert response.is_success
        assert response.headers["cache-control"] == "no-store", url


def test_get_me_links_is_unchanged(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    student = _student(storage, me)
    _practiced(storage, student, TODAY)

    [listed] = _get(api, "/api/v1/me/links")["students"]

    assert set(listed) == {"id", "name", "linked_at"}


# OpenAPI


def _openapi(api: TestClient) -> dict[str, Any]:
    return api.get("/openapi.json").json()


def _deref(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        node = schema["components"]["schemas"][node["$ref"].rsplit("/", 1)[1]]
    return node


def _response(schema: dict[str, Any], path: str) -> dict[str, Any]:
    ok = schema["paths"][path]["get"]["responses"]["200"]
    return _deref(schema, ok["content"]["application/json"]["schema"])


def _options(schema: dict[str, Any], node: dict[str, Any]) -> list[dict[str, Any]]:
    """The alternatives of a nullable field, dereferenced."""
    return [_deref(schema, n) for n in node.get("anyOf", [node])]


def _state_values(schema: dict[str, Any], node: dict[str, Any]) -> set[str | None]:
    values: set[str | None] = set()
    for option in _options(schema, node):
        if option.get("type") == "null":
            values.add(None)
        else:
            values |= set(option["enum"])
    return values


def _object_of(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    return next(o for o in _options(schema, node) if "properties" in o)


def test_openapi_has_the_exact_list_shape(api: TestClient) -> None:
    schema = _openapi(api)

    body = _response(schema, STUDENTS)
    item = _deref(schema, body["properties"]["students"]["items"])

    assert set(body["properties"]) == {"students", "total"}
    assert set(item["properties"]) == {"id", "name", "today"}
    assert _state_values(schema, item["properties"]["today"]) == {"practiced", "rest", None}


def test_openapi_has_the_exact_card_shape(api: TestClient) -> None:
    schema = _openapi(api)

    body = _response(schema, CARD)
    day = _deref(schema, body["properties"]["days"]["items"])
    length = _object_of(schema, day["properties"]["length"])
    position = _object_of(schema, body["properties"]["last_asana"])

    assert set(body["properties"]) == {"id", "name", "days", "last_asana", "next_asanas", "quiet"}
    assert _deref(schema, body["properties"]["next_asanas"]["items"]) == position
    assert set(day["properties"]) == {"date", "state", "length"}
    assert _state_values(schema, day["properties"]["state"]) == {"practiced", "rest", None}
    assert set(length["properties"]) == {"series", "end", "first_part"}
    assert set(position["properties"]) == {"series", "last"}


def test_openapi_reuses_length_and_position_and_names_the_new_outputs(api: TestClient) -> None:
    schemas = _openapi(api)["components"]["schemas"]

    assert {"StudentsOut", "StudentCardOut", "DayOut", "Length", "PositionOut"} <= set(schemas)


def test_openapi_takes_only_offset_and_limit(api: TestClient) -> None:
    operation = _openapi(api)["paths"][STUDENTS]["get"]

    names = {p["name"] for p in operation["parameters"]}

    assert names - {"Authorization"} == {"offset", "limit"}


def test_openapi_adds_no_error_code(api: TestClient) -> None:
    codes = _openapi(api)["components"]["schemas"]["ErrorCode"]["enum"]

    assert "not_linked" in codes
    assert not [c for c in codes if "student" in c or "teacher_view" in c]


def test_the_flag_and_the_zone_are_nowhere_in_openapi(api: TestClient) -> None:
    text = json.dumps(_openapi(api))

    assert "quiet_note_agreed" not in text
    assert "linked_on" not in text


def test_the_mini_apps_contract_has_both_reads_and_no_flag() -> None:
    """The TS client is generated from this file: `npm run typecheck` builds against it."""
    path = Path(__file__).resolve().parents[3] / "miniapp" / "src" / "api" / "openapi.json"
    raw = path.read_text()
    paths = json.loads(raw)["paths"]

    assert "get" in paths[STUDENTS]
    assert "get" in paths[CARD]
    assert "quiet_note_agreed" not in raw
