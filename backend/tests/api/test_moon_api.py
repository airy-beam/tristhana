import json
import time as clock
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FakeNotifier, InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.notifications import send_instant
from tristhana.main import create_app
from tristhana.moon import ALGO_VERSION
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
TICK = "tick-token-for-tests"


def _auth(user_id: int = 42) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(clock.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    s = InMemoryStorage()
    today = datetime.now(UTC).date()
    s.moon_repo.days_by_location["mysuru"] = [
        MoonDay(today + timedelta(days=5), MoonDayKind.PURNIMA),
        MoonDay(today + timedelta(days=20), MoonDayKind.KSHAYA_AMAVASYA),
    ]
    return s


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def api(storage: InMemoryStorage, notifier: FakeNotifier) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        internal_tick_token=SecretStr(TICK),
    )
    with TestClient(create_app(settings, storage, notifier)) as client:
        yield client


def test_cities_are_public_and_cacheable(api: TestClient) -> None:
    first = api.get("/api/v1/moon/cities")

    assert first.status_code == 200
    assert first.json()[0] == {
        "slug": "mysuru",
        "name_en": "Mysuru",
        "name_ru": "Майсур",
        "timezone": "Asia/Kolkata",
    }
    again = api.get("/api/v1/moon/cities", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304


def test_moon_days_default_to_mysuru(api: TestClient) -> None:
    body = api.get("/api/v1/me/moon-days", headers=_auth()).json()

    assert body["location"] == {"slug": "mysuru", "explicit": False}
    assert [(d["kind"], d["phase"]) for d in body["days"]] == [
        ("purnima", "purnima"),
        ("kshaya_amavasya", "amavasya"),
    ]


def test_moon_location_round_trip(api: TestClient) -> None:
    chosen = api.put("/api/v1/me/moon-location", json={"slug": "almaty"}, headers=_auth())
    unknown = api.put("/api/v1/me/moon-location", json={"slug": "atlantis"}, headers=_auth())
    back = api.put("/api/v1/me/moon-location", json={"slug": None}, headers=_auth())

    assert chosen.json() == {"slug": "almaty", "explicit": True}
    assert (unknown.status_code, unknown.json()) == (422, {"code": "unknown_location"})
    assert back.json() == {"slug": "mysuru", "explicit": False}


def test_notification_settings_round_trip(api: TestClient) -> None:
    defaults = api.get("/api/v1/me/notification-settings", headers=_auth()).json()
    body: dict[str, Any] = {
        "moon": {"offsets": [1, 3], "at": "07:00:00"},
        "quiet": {"start": "23:00:00", "end": "06:00:00"},
        "daily_cap": 2,
    }
    saved = api.put("/api/v1/me/notification-settings", json=body, headers=_auth())
    bad = api.put(
        "/api/v1/me/notification-settings",
        json=body | {"moon": {"offsets": [1], "at": "07:05:00"}},
        headers=_auth(),
    )

    assert defaults["moon"] == {"offsets": [1, 7], "at": "19:00:00"}
    assert defaults["timezone"] is None
    practice = {"on": None, "at": "10:00:00", "days": [1, 2, 3, 4, 5, 7]}
    assert defaults["practice"] == practice
    question = {"weekday": 6, "reminders_on": False}  # PR-09: the day off is not chosen yet
    assert saved.json() == body | {
        "timezone": None,
        "practice": practice,
        "day_off_question": question,
    }  # omitted: kept
    assert (bad.status_code, bad.json()) == (422, {"code": "invalid_settings"})


def test_tick_is_hidden_without_the_token(api: TestClient) -> None:
    assert api.post("/internal/tick").status_code == 404
    assert (
        api.post("/internal/tick", headers={"X-Tristhana-Tick-Token": "wrong"}).status_code == 404
    )
    assert "/internal/tick" not in api.get("/openapi.json").json()["paths"]


def test_tick_sends_a_due_reminder(
    storage: InMemoryStorage, notifier: FakeNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tristhana.main

    moon_date = datetime.now(UTC).date() + timedelta(days=5)
    evening = send_instant(moon_date - timedelta(days=1), time(19), "Asia/Almaty")
    for year in range(evening.year - 1, evening.year + 3):  # calendars already computed
        for city in ("mysuru", "almaty"):
            storage.moon_repo.ledger[(city, year)] = ALGO_VERSION

    class Frozen:
        def now(self) -> datetime:
            return evening

    monkeypatch.setattr(tristhana.main, "SystemClock", Frozen)
    monkeypatch.setattr(tristhana.main, "GeneratorMoonCalculator", _NoCompute)
    settings = Settings(
        app_env="test", telegram_bot_token=SecretStr(TOKEN), internal_tick_token=SecretStr(TICK)
    )
    with TestClient(create_app(settings, storage, notifier)) as client:
        client.get("/api/v1/me", headers=_auth())
        [account] = storage.repo.accounts.values()
        storage.repo.accounts[account.id] = replace(account, timezone="Asia/Almaty")
        body = client.post("/internal/tick", headers={"X-Tristhana-Tick-Token": TICK}).json()

    assert body["sent"] == 1
    [(recipient, reminder)] = notifier.moon
    assert (recipient.telegram_id, reminder.days_before, reminder.moon_day.date) == (
        "42",
        1,
        moon_date,
    )


class _NoCompute:
    version = ALGO_VERSION

    async def compute_year(self, location: object, year: int) -> list[MoonDay]:
        return []


def test_practice_reminder_settings_round_trip(api: TestClient) -> None:
    current = api.get("/api/v1/me/notification-settings", headers=_auth()).json()
    on = current | {"practice": {"on": True, "at": "20:00:00", "days": [1, 2, 3, 4, 5, 6]}}
    del on["timezone"]

    saved = api.put("/api/v1/me/notification-settings", json=on, headers=_auth())
    no_days = api.put(
        "/api/v1/me/notification-settings",
        json=on | {"practice": on["practice"] | {"days": []}},
        headers=_auth(),
    )
    in_quiet = api.put(
        "/api/v1/me/notification-settings",
        json=on | {"practice": on["practice"] | {"at": "23:00:00"}},
        headers=_auth(),
    )
    moon_only = api.put(
        "/api/v1/me/notification-settings",
        json={k: v for k, v in on.items() if k != "practice"},
        headers=_auth(),
    )

    assert saved.json()["practice"] == on["practice"]
    assert no_days.status_code == 422
    assert (in_quiet.status_code, in_quiet.json()) == (422, {"code": "invalid_settings"})
    assert moon_only.json()["practice"] == on["practice"]  # omitted: unchanged


def test_stats_for_the_owner(api: TestClient, storage: InMemoryStorage) -> None:
    from tristhana.domain.days import DayLog, DayStatus

    api.get("/api/v1/me", headers=_auth())
    [account] = storage.repo.accounts.values()
    today = datetime.now(UTC).date()
    storage.day_repo.rows[(account.id, today - timedelta(days=1))] = (
        DayLog(today - timedelta(days=1), DayStatus.LADIES),
        None,
    )

    body = api.get("/api/v1/me/stats", headers=_auth()).json()
    bad = api.get("/api/v1/me/stats", params={"year": 1999}, headers=_auth())

    assert body["first_year"] == (today - timedelta(days=1)).year
    assert len(body["months"]) == 12
    assert body["moon"]["location"] == "mysuru"
    assert "ladies" in body["cells"]  # the owner's own data
    assert body["runs"] == {"current": None, "longest": 0}
    assert set(body["months"][0]["contexts"]) == {"mysore", "led", "private", "self"}
    assert (bad.status_code, bad.json()) == (422, {"code": "invalid_year"})
    assert api.get("/api/v1/me/stats").status_code == 401
