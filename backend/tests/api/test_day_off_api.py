"""The weekly day off over the API (PR-09, ADR-0022): PUT /me/day-off, the one-time
question, and auto-rest on /me/days and /me/stats."""

import json
import time as clock
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
# The fake accounts are created on 2026-10-18 (tests.fakes.NOW): Saturday Oct 24 is after.
WEEK = {"from": "2026-10-19", "to": "2026-10-25"}


def _auth() -> dict[str, str]:
    profile = {"id": 42, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(clock.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def api() -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, InMemoryStorage())) as client:
        client.post("/api/v1/me/device-timezone", json={"timezone": "Asia/Almaty"}, headers=_auth())
        yield client


def _put(api: TestClient, day_off: Any) -> Any:
    return api.put("/api/v1/me/day-off", json={"day_off": day_off}, headers=_auth())


def test_day_off_is_null_until_chosen(api: TestClient) -> None:
    assert api.get("/api/v1/me", headers=_auth()).json()["day_off"] is None
    _put(api, [])
    assert api.get("/api/v1/me", headers=_auth()).json()["day_off"] == []
    _put(api, [6])
    assert api.get("/api/v1/me", headers=_auth()).json()["day_off"] == [6]


def test_put_day_off_returns_the_reminder_days_that_follow(api: TestClient) -> None:
    out = _put(api, [7])
    assert out.status_code == 200
    assert out.json() == {"day_off": [7], "practice_days": [1, 2, 3, 4, 5, 6]}
    weekend = _put(api, [6, 7]).json()
    assert weekend == {"day_off": [6, 7], "practice_days": [1, 2, 3, 4, 5]}


@pytest.mark.parametrize("day_off", [[5, 6, 7], [8], [0], [6, 6], None])
def test_invalid_day_off_is_422(api: TestClient, day_off: Any) -> None:
    out = _put(api, day_off)
    assert out.status_code == 422
    if day_off is not None:  # null fails the schema itself
        assert out.json() == {"code": "invalid_day_off"}


def test_the_question_shows_once_until_answered_or_dismissed(api: TestClient) -> None:
    def question() -> Any:
        return api.get("/api/v1/me/notification-settings", headers=_auth()).json()[
            "day_off_question"
        ]

    assert question() == {"weekday": 6, "reminders_on": False}
    assert api.delete("/api/v1/me/day-off-question", headers=_auth()).status_code == 204
    assert api.delete("/api/v1/me/day-off-question", headers=_auth()).status_code == 204
    assert question() is None


def test_answering_the_question_hides_it(api: TestClient) -> None:
    _put(api, [6])
    settings = api.get("/api/v1/me/notification-settings", headers=_auth()).json()
    assert settings["day_off_question"] is None


def test_days_carry_auto_rest_for_unlogged_days(api: TestClient) -> None:
    _put(api, [6])
    days = api.get("/api/v1/me/days", params=WEEK, headers=_auth()).json()
    assert days["auto"] == [{"date": "2026-10-24", "kind": "day_off", "also_day_off": False}]
    assert days["moon_location"] == "mysuru"
    api.put("/api/v1/me/days/2026-10-24", json={"status": "practiced"}, headers=_auth())
    days = api.get("/api/v1/me/days", params=WEEK, headers=_auth()).json()
    assert days["auto"] == []  # a log always wins


def test_stats_count_auto_days_as_rest(api: TestClient) -> None:
    _put(api, [6])
    stats = api.get("/api/v1/me/stats", params={"year": 2026}, headers=_auth()).json()
    october = stats["months"][9]
    assert {"date": "2026-10-24", "kind": "day_off", "also_day_off": False} in stats["auto"]
    assert october["auto"] >= 1
    assert october["rest"]["rest"] == october["auto"]
    assert stats["cells"][296] == "none"  # Oct 24: cells keep their enum for old bundles
