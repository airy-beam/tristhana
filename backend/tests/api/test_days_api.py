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


def _auth(user_id: int = 42) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        cors_origins="https://tristhana.web.app",
    )
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _today_moscow() -> date:
    # A new account has no zone: ru → provisional Europe/Moscow (UTC+3, no DST).
    return (datetime.now(UTC) + timedelta(hours=3)).date()


def test_get_days_defaults_to_this_week(api: TestClient) -> None:
    body = api.get("/api/v1/me/days", headers=_auth()).json()

    assert body == {
        "today": _today_moscow().isoformat(),
        "timezone_known": False,
        "days": [],
        "auto": [],
        "moon_location": "mysuru",
    }


def test_put_get_delete_round_trip_including_ladies(api: TestClient) -> None:
    today = _today_moscow()
    put = api.put(f"/api/v1/me/days/{today}", json={"status": "ladies"}, headers=_auth())

    assert put.status_code == 200
    assert put.json() == {"date": today.isoformat(), "status": "ladies", "practices": []}
    assert api.get("/api/v1/me/days", headers=_auth()).json()["days"] == [put.json()]

    for _ in range(2):  # idempotent
        assert api.delete(f"/api/v1/me/days/{today}", headers=_auth()).status_code == 204
    assert api.get("/api/v1/me/days", headers=_auth()).json()["days"] == []


def test_days_are_private_to_their_owner(api: TestClient) -> None:
    today = _today_moscow()
    api.put(f"/api/v1/me/days/{today}", json={"status": "practiced"}, headers=_auth(42))

    assert api.get("/api/v1/me/days", headers=_auth(43)).json()["days"] == []


@pytest.mark.parametrize(
    ("day", "body", "status", "code"),
    [
        (date(2999, 1, 1), {"status": "rest"}, 422, "date_in_future"),
        (date(1999, 12, 31), {"status": "rest"}, 422, "date_too_early"),
    ],
)
def test_put_rejects_dates(
    api: TestClient, day: date, body: dict[str, Any], status: int, code: str
) -> None:
    response = api.put(f"/api/v1/me/days/{day}", json=body, headers=_auth())

    assert (response.status_code, response.json()) == (status, {"code": code})


def test_put_rejects_unknown_status(api: TestClient) -> None:
    response = api.put(
        f"/api/v1/me/days/{_today_moscow()}", json={"status": "nap"}, headers=_auth()
    )

    assert response.status_code == 422


def test_range_validation(api: TestClient) -> None:
    response = api.get(
        "/api/v1/me/days", params={"from": "2026-10-19", "to": "2026-10-01"}, headers=_auth()
    )

    assert (response.status_code, response.json()) == (422, {"code": "invalid_range"})


def test_needs_auth(api: TestClient) -> None:
    assert api.get("/api/v1/me/days").status_code == 401
    assert api.put("/api/v1/me/days/2026-10-18", json={"status": "rest"}).status_code == 401


def test_database_down_is_503(api: TestClient, storage: InMemoryStorage) -> None:
    api.get("/api/v1/me", headers=_auth())  # account exists
    storage.day_repo.down = True

    assert api.get("/api/v1/me/days", headers=_auth()).json() == {"code": "unavailable"}


def test_cors_allows_put(api: TestClient) -> None:
    response = api.options(
        "/api/v1/me/days/2026-10-18",
        headers={
            "Origin": "https://tristhana.web.app",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_openapi_lists_the_new_error_codes(api: TestClient) -> None:
    codes = api.get("/openapi.json").json()["components"]["schemas"]["ErrorCode"]["enum"]

    assert {"invalid_range", "date_in_future", "date_too_early"} <= set(codes)
