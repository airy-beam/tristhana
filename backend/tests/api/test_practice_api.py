import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"


def _auth(user_id: int = 42) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def api() -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, InMemoryStorage())) as client:
        yield client


def _today() -> str:
    return (datetime.now(UTC) + timedelta(hours=3)).date().isoformat()  # provisional Moscow


def _practiced(api: TestClient, day: str) -> None:
    put = api.put(f"/api/v1/me/days/{day}", json={"status": "practiced"}, headers=_auth())
    assert put.status_code == 200


def _put(api: TestClient, day: str, body: dict[str, Any]) -> Any:
    return api.put(f"/api/v1/me/days/{day}/practices/1", json=body, headers=_auth())


def test_catalog_is_public_cacheable_and_confirmed_only(api: TestClient) -> None:
    first = api.get("/api/v1/catalog")

    assert first.status_code == 200
    body = first.json()
    assert [s["slug"] for s in body["series"]] == [
        "primary",
        "intermediate",
        "advanced-a",
        "advanced-b",
    ]
    primary = body["series"][0]
    assert primary["halves_split"] == "navasana"
    assert {"key": "janu-sirsasana-c", "latin": "Janu Sirsasana C", "ru": "Джану Ширшасана C"} in (
        primary["stops"]
    )
    assert first.headers["etag"] == f'"{body["version"]}"'
    for header in (first.headers["etag"], f'"x", W/{first.headers["etag"]}'):
        assert api.get("/api/v1/catalog", headers={"If-None-Match": header}).status_code == 304


def test_put_round_trip_and_days_include_it(api: TestClient) -> None:
    day = _today()
    _practiced(api, day)
    body = {
        "context": "mysore",
        "online": False,
        "length": {
            "series": ["primary", "intermediate"],
            "end": "pasasana",
            "first_part": "first_half",
        },
        "duration_min": 120,
        "start_time": None,
    }

    saved = _put(api, day, body)
    days = api.get("/api/v1/me/days", headers=_auth()).json()["days"]

    assert saved.status_code == 200
    assert saved.json() == body | {"slot": 1, "timezone": None}
    assert days[-1]["practices"] == [saved.json()]


def test_full_series_end_is_normalised(api: TestClient) -> None:
    day = _today()
    _practiced(api, day)

    saved = _put(api, day, {"length": {"series": ["primary"], "end": "setu-bandhasana"}})

    assert saved.json()["length"] == {"series": ["primary"], "end": None, "first_part": None}


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"length": {"series": ["primary", "advanced-a"]}}, "invalid_length"),
        ({"length": {"series": ["primary"], "end": "dandasana"}}, "invalid_length"),
        ({"duration_min": 0}, None),
        ({"start_time": "06:30+05:00"}, "invalid_practice"),
        ({"start_time": "06:30"}, "timezone_unknown"),  # the account has no zone yet
    ],
)
def test_put_rejects(api: TestClient, body: dict[str, Any], code: str | None) -> None:
    day = _today()
    _practiced(api, day)

    response = _put(api, day, body)

    assert response.status_code == 422
    if code:  # else pydantic's own validation error
        assert response.json() == {"code": code}


def test_self_practice_is_never_online(api: TestClient) -> None:
    day = _today()
    _practiced(api, day)

    saved = _put(api, day, {"context": "self", "online": True})

    assert (saved.status_code, saved.json()["online"]) == (200, False)


def test_put_needs_a_practiced_day(api: TestClient) -> None:
    day = _today()
    api.put(f"/api/v1/me/days/{day}", json={"status": "rest"}, headers=_auth())

    response = _put(api, day, {"duration_min": 60})

    assert (response.status_code, response.json()) == (409, {"code": "day_not_practiced"})


def test_only_slot_one_for_now(api: TestClient) -> None:
    day = _today()
    _practiced(api, day)

    response = api.put(f"/api/v1/me/days/{day}/practices/2", json={}, headers=_auth())

    assert response.status_code == 422


def test_presets_and_delete(api: TestClient) -> None:
    yesterday = (datetime.fromisoformat(_today()) - timedelta(days=1)).date().isoformat()
    _practiced(api, yesterday)
    _put(
        api,
        yesterday,
        {"context": "led", "length": {"series": ["intermediate"], "end": "karandavasana"}},
    )

    presets = api.get(f"/api/v1/me/days/{_today()}/practice-presets", headers=_auth()).json()
    deleted = api.delete(f"/api/v1/me/days/{yesterday}/practices/1", headers=_auth())
    again = api.delete(f"/api/v1/me/days/{yesterday}/practices/1", headers=_auth())

    assert presets["last"]["context"] == "led"
    assert [p["kind"] for p in presets["presets"]] == [
        "short",
        "half_primary",
        "full_primary",
        "recent",
    ]
    assert (deleted.status_code, again.status_code) == (204, 204)


def test_practice_endpoints_need_auth(api: TestClient) -> None:
    assert api.put(f"/api/v1/me/days/{_today()}/practices/1", json={}).status_code == 401
    assert api.get(f"/api/v1/me/days/{_today()}/practice-presets").status_code == 401


def test_openapi_lists_the_new_error_codes(api: TestClient) -> None:
    codes = api.get("/openapi.json").json()["components"]["schemas"]["ErrorCode"]["enum"]

    assert {"day_not_practiced", "invalid_length", "invalid_practice", "timezone_unknown"} <= set(
        codes
    )
