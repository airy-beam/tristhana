"""Diary endpoints (PR-07, spec §4): PUT/DELETE on a day's note, `notes` on /me/days (any
status, also unlogged and unreadable), `Cache-Control: no-store`, the text never echoed in a
422 (domain length check, `input` stripped from validation errors), 413 over 16 KiB, and the
OpenAPI contract."""

import json
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
SECRET_WORDS = "my very private words about practice"


def _auth(user_id: int = 42) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _today() -> date:
    return (datetime.now(UTC) + timedelta(hours=3)).date()  # provisional Moscow


def _url(day: date | str) -> str:
    return f"/api/v1/me/days/{day}/note"


def _put(api: TestClient, day: date | str, text: Any, user_id: int = 42) -> Any:
    return api.put(_url(day), json={"text": text}, headers=_auth(user_id))


def _get(api: TestClient, user_id: int = 42, params: dict[str, str] | None = None) -> Any:
    return api.get("/api/v1/me/days", params=params or {}, headers=_auth(user_id))


def _notes(api: TestClient, user_id: int = 42) -> list[dict[str, Any]]:
    return _get(api, user_id).json()["notes"]


def _status(api: TestClient, day: date, status: str) -> None:
    put = api.put(f"/api/v1/me/days/{day}", json={"status": status}, headers=_auth())
    assert put.status_code == 200


# Auth


def test_note_endpoints_need_auth(api: TestClient) -> None:
    day = _today()

    assert api.put(_url(day), json={"text": "hi"}).status_code == 401
    assert api.delete(_url(day)).status_code == 401


# PUT


def test_put_saves_and_returns_the_normalised_note(api: TestClient) -> None:
    day = _today()

    response = _put(api, day, "  Felt light.\r\nTeacher: soft gaze.\n ")

    assert response.status_code == 200
    assert response.json() == {
        "date": day.isoformat(),
        "text": "Felt light.\nTeacher: soft gaze.",
        "unreadable": False,
    }
    assert _notes(api) == [response.json()]


def test_put_replaces_the_note(api: TestClient) -> None:
    day = _today()
    _put(api, day, "first")

    _put(api, day, "second")

    assert [n["text"] for n in _notes(api)] == ["second"]


def test_a_blank_put_deletes(api: TestClient) -> None:
    day = _today()
    _put(api, day, "something")

    response = _put(api, day, "  \n ")

    assert response.status_code == 200
    assert response.json() == {"date": day.isoformat(), "text": None, "unreadable": False}
    assert _notes(api) == []


def test_2000_code_points_fit(api: TestClient) -> None:
    response = _put(api, _today(), "🧘" * 2000)

    assert response.status_code == 200
    assert response.json()["text"] == "🧘" * 2000


def test_too_long_is_422_and_never_echoes_the_text(api: TestClient) -> None:
    day = _today()
    _put(api, day, "kept")
    text = (SECRET_WORDS + " ") * 60  # 2220 code points

    response = _put(api, day, text)

    assert response.status_code == 422
    assert response.json() == {"code": "note_too_long"}
    assert "private" not in response.text
    assert [n["text"] for n in _notes(api)] == ["kept"]


@pytest.mark.parametrize("body", [{"text": {"x": SECRET_WORDS}}, {"text": [SECRET_WORDS]}, {}])
def test_a_malformed_body_is_422_and_never_echoes_it(api: TestClient, body: Any) -> None:
    response = api.put(_url(_today()), json=body, headers=_auth())

    assert response.status_code == 422
    assert "private" not in response.text
    assert "input" not in json.dumps(response.json())


def test_validation_errors_never_echo_the_input_anywhere(api: TestClient) -> None:
    # `api/errors` strips `input` from every validation error, not only the note's.
    response = api.put(
        f"/api/v1/me/days/{_today()}", json={"status": SECRET_WORDS}, headers=_auth()
    )

    assert response.status_code == 422
    assert "private" not in response.text


def test_a_body_over_16_kib_is_413(api: TestClient) -> None:
    response = _put(api, _today(), "a" * (17 * 1024))

    assert response.status_code == 413
    assert "aaaa" not in response.text
    assert _notes(api) == []


def test_a_chunked_body_over_16_kib_is_413_before_it_is_read(api: TestClient) -> None:
    # No Content-Length: the cap is counted while streaming (`api/body_limit`).
    chunks = iter([b'{"text": "', b"a" * (17 * 1024), b'"}'])
    headers = _auth() | {"Content-Type": "application/json"}

    response = api.put(_url(_today()), content=chunks, headers=headers)

    assert response.status_code == 413
    assert response.json() == {"code": "body_too_large"}
    assert _notes(api) == []


def test_a_future_date_is_422(api: TestClient) -> None:
    response = _put(api, _today() + timedelta(days=2), "tomorrow's plan")

    assert response.status_code == 422
    assert response.json() == {"code": "date_in_future"}
    assert "plan" not in response.text


def test_before_2000_is_422(api: TestClient) -> None:
    response = _put(api, "1999-12-31", "old")

    assert (response.status_code, response.json()) == (422, {"code": "date_too_early"})


def test_the_text_never_travels_in_the_url(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/me/days/{date}/note"]["put"]

    assert [p["name"] for p in operation.get("parameters", [])] == ["date"]
    assert "requestBody" in operation


# DELETE


def test_delete_is_204_and_idempotent(api: TestClient) -> None:
    day = _today()
    _put(api, day, "something")

    first = api.delete(_url(day), headers=_auth())
    again = api.delete(_url(day), headers=_auth())

    assert (first.status_code, again.status_code) == (204, 204)
    assert _notes(api) == []


def test_delete_keeps_the_day(api: TestClient) -> None:
    day = _today()
    _status(api, day, "practiced")
    _put(api, day, "something")

    deleted = api.delete(_url(day), headers=_auth())

    assert deleted.status_code == 204
    assert [d["status"] for d in _get(api).json()["days"]] == ["practiced"]


# GET /me/days


def test_days_carry_notes_for_logged_and_unlogged_days(api: TestClient) -> None:
    today = _today()
    yesterday = today - timedelta(days=1)
    _status(api, today, "rest")
    _put(api, today, "rested")
    _put(api, yesterday, "never logged")

    body = _get(api).json()

    assert body["notes"] == [
        {"date": yesterday.isoformat(), "text": "never logged", "unreadable": False},
        {"date": today.isoformat(), "text": "rested", "unreadable": False},
    ]
    assert [d["date"] for d in body["days"]] == [today.isoformat()]
    assert "note" not in body["days"][0]  # notes live beside the days, not on them


def test_days_carry_an_unreadable_note(api: TestClient, storage: InMemoryStorage) -> None:
    from tristhana.domain.diary import DiaryNote

    day = _today()
    _put(api, day, "will be unreadable")
    [key] = storage.day_repo.diary_rows
    storage.day_repo.diary_rows[key] = DiaryNote(None)

    assert _notes(api) == [{"date": day.isoformat(), "text": None, "unreadable": True}]


def test_days_have_an_empty_notes_list_by_default(api: TestClient) -> None:
    assert _notes(api) == []


def test_notes_follow_the_requested_range(api: TestClient) -> None:
    today = _today()
    old = today - timedelta(days=20)
    _put(api, old, "older")
    _put(api, today, "today")

    week = _notes(api)
    window = {"from": str(old), "to": str(old + timedelta(days=1))}  # the API's query names
    earlier = _get(api, params=window).json()["notes"]

    assert [n["text"] for n in week] == ["today"]
    assert [n["text"] for n in earlier] == ["older"]


@pytest.mark.parametrize("status", ["practiced", "rest", "moon", "ladies", "sick", "travel"])
def test_a_status_change_or_clearing_keeps_the_note(api: TestClient, status: str) -> None:
    day = _today()
    _status(api, day, "skipped")
    _put(api, day, "kept")

    _status(api, day, status)
    after_change = _notes(api)
    api.delete(f"/api/v1/me/days/{day}", headers=_auth())

    assert [n["text"] for n in after_change] == ["kept"]
    assert [n["text"] for n in _notes(api)] == ["kept"]


def test_notes_are_private_to_their_owner(api: TestClient) -> None:
    _put(api, _today(), "mine", user_id=42)

    assert _notes(api, user_id=43) == []


def test_responses_with_notes_are_never_cached(api: TestClient) -> None:
    day = _today()

    put = _put(api, day, "private")
    days = _get(api)

    assert put.headers.get("cache-control") == "no-store"
    assert days.headers.get("cache-control") == "no-store"


# OpenAPI


def test_openapi_has_the_paths_the_shape_and_the_error_code(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()
    schemas = schema["components"]["schemas"]
    path = "/api/v1/me/days/{date}/note"

    assert "note_too_long" in schemas["ErrorCode"]["enum"]
    assert path in schema["paths"]
    assert {"put", "delete"} <= set(schema["paths"][path])
    assert set(schemas["DayNoteOut"]["properties"]) == {"date", "text", "unreadable"}
    assert "notes" in schemas["Days"]["properties"]
    assert "notes" not in schemas["Day"]["properties"]
    body = schema["paths"][path]["put"]["requestBody"]["content"]["application/json"]["schema"]
    request = schemas[body["$ref"].rsplit("/", 1)[-1]] if "$ref" in body else body
    assert set(request["properties"]) == {"text"}
    assert "maxLength" not in json.dumps(request)  # checked in the domain, never echoed
