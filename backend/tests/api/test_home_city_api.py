"""MD-04 + ID-06 over HTTP: `Me.home_city`, PATCH /me with a city, the moon-days FYI."""

import json
import time as clock
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ASTANA = {"slug": "astana", "name_en": "Astana", "name_ru": "Астана", "timezone": "Asia/Almaty"}


def _auth() -> dict[str, str]:
    profile = {"id": 42, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(clock.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _patch(api: TestClient, body: dict[str, Any]) -> Any:
    return api.patch("/api/v1/me", json=body, headers=_auth())


def test_a_new_account_has_no_city_and_has_not_answered(api: TestClient) -> None:
    me = api.get("/api/v1/me", headers=_auth()).json()

    assert (me["home_city"], me["home_city_chosen"]) == (None, False)


def test_picking_a_city_sets_its_zone(api: TestClient) -> None:
    me = _patch(api, {"home_city": "astana"}).json()

    assert (me["home_city"], me["home_city_chosen"], me["timezone"]) == (
        ASTANA,
        True,
        "Asia/Almaty",
    )


def test_the_patch_matrix(api: TestClient) -> None:
    unknown = _patch(api, {"home_city": "atlantis"})
    conflict = _patch(api, {"home_city": "astana", "timezone": "Europe/Moscow"})
    not_listed = _patch(api, {"home_city": None, "timezone": "Asia/Bangkok"}).json()
    astana = _patch(api, {"home_city": "astana"}).json()
    travel = _patch(api, {"timezone": "Asia/Bangkok"}).json()

    assert (unknown.status_code, unknown.json()) == (422, {"code": "unknown_city"})
    assert (conflict.status_code, conflict.json()) == (422, {"code": "invalid_timezone"})
    assert (not_listed["home_city"], not_listed["home_city_chosen"]) == (None, True)
    assert not_listed["timezone"] == "Asia/Bangkok"
    assert astana["home_city"] == ASTANA
    assert (travel["home_city"], travel["home_city_chosen"], travel["timezone"]) == (
        None,
        True,
        "Asia/Bangkok",
    )


def test_not_now_answers_the_nudge_and_keeps_the_zone(api: TestClient) -> None:
    _patch(api, {"timezone": "Asia/Almaty"})

    me = _patch(api, {"home_city": None}).json()

    assert (me["home_city"], me["home_city_chosen"], me["timezone"]) == (None, True, "Asia/Almaty")


def test_moon_days_add_the_home_citys_other_date(api: TestClient, storage: InMemoryStorage) -> None:
    today = datetime.now(UTC).date()
    full, new = today + timedelta(days=5), today + timedelta(days=20)
    storage.moon_repo.days_by_location["mysuru"] = [
        MoonDay(full, MoonDayKind.PURNIMA),
        MoonDay(new, MoonDayKind.AMAVASYA),
    ]
    storage.moon_repo.days_by_location["astana"] = [
        MoonDay(full - timedelta(days=1), MoonDayKind.PURNIMA),
        MoonDay(new, MoonDayKind.AMAVASYA),
    ]
    before = api.get("/api/v1/me/moon-days", headers=_auth()).json()
    _patch(api, {"home_city": "astana"})

    after = api.get("/api/v1/me/moon-days", headers=_auth()).json()

    assert before["home"] is None
    assert [d["home_date"] for d in before["days"]] == [None, None]
    assert after["home"] == ASTANA
    assert [d["home_date"] for d in after["days"]] == [
        (full - timedelta(days=1)).isoformat(),
        None,
    ]
