"""ST-05 `GET /api/v1/me/check-in-trends` (spec §5, §8): 401 without auth; an empty account;
too few; a full payload with null cells; the minimums; the OpenAPI contract. Real use case
over an in-memory facts fake, a frozen clock."""

import json
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FixedClock, InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.check_in_trends import MIN_BUCKET, MIN_TOTAL, ScaleDay, TrendFacts
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ME_TG = 42
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
URL = "/api/v1/me/check-in-trends"
FULL = date(2026, 10, 26)
NONE = {"mood": None, "energy": None, "effort": None}


def _auth(user_id: int = ME_TG) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Anna", "language_code": "en"}
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


def _me(api: TestClient, storage: InMemoryStorage) -> UUID:
    assert api.get("/api/v1/me", headers=_auth()).status_code == 200
    return storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(ME_TG))]


def _get(api: TestClient) -> dict[str, Any]:
    response = api.get(URL, headers=_auth())
    assert response.status_code == 200
    return response.json()


def _days(start: date, n: int, energy: int) -> list[ScaleDay]:
    return [ScaleDay(start + timedelta(days=i), None, energy, 3) for i in range(n)]


def test_trends_need_auth(api: TestClient) -> None:
    assert api.get(URL).status_code == 401


def test_an_empty_account_gets_nothing_but_the_window(
    api: TestClient, storage: InMemoryStorage
) -> None:
    _me(api, storage)

    assert _get(api) == {
        "from": "2025-12-01",
        "to": "2026-11-11",
        "total": 0,
        "enough": False,
        "min_total": MIN_TOTAL,
        "min_bucket": MIN_BUCKET,
        "months": [],
        "weekdays": None,
        "moon": None,
    }


def test_too_few_check_ins_send_no_average(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    days = _days(date(2026, 10, 1), MIN_TOTAL - 1, 4)
    storage.check_in_trends.by_account[me] = TrendFacts(tuple(days), ())

    body = _get(api)

    assert (body["total"], body["enough"]) == (MIN_TOTAL - 1, False)
    assert (body["months"], body["weekdays"], body["moon"]) == ([], None, None)


def test_a_full_payload_carries_averages_counts_and_null_cells(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    near = [ScaleDay(FULL + timedelta(days=d), None, 5, 3) for d in (-1, 0, 1)]
    near += [ScaleDay(date(2026, 9, 26) + timedelta(days=d), None, 4, 3) for d in (-1, 1)]
    days = [*near, *_days(date(2026, 10, 1), 10, 2)]
    moon = (
        MoonDay(FULL, MoonDayKind.PURNIMA),
        MoonDay(date(2026, 9, 26), MoonDayKind.PURNIMA),
        MoonDay(date(2026, 11, 9), MoonDayKind.AMAVASYA),
    )
    storage.check_in_trends.by_account[me] = TrendFacts(tuple(days), moon)

    body = _get(api)

    assert (body["total"], body["enough"]) == (15, True)
    assert [m["month"] for m in body["months"]] == [
        "2025-12",
        *(f"2026-{m:02d}" for m in range(1, 12)),
    ]
    october = body["months"][10]
    assert october == {
        "month": "2026-10",
        "mood": None,
        "energy": {"mean": 2.7, "n": 13},
        "effort": {"mean": 3.0, "n": 13},
    }
    assert body["months"][0] == {"month": "2025-12", **NONE}
    assert body["weekdays"] is None  # no weekday has five check-ins: the section is left out
    assert body["moon"] == {
        "location": "mysuru",
        "full": {"mood": None, "energy": {"mean": 4.6, "n": 5}, "effort": {"mean": 3.0, "n": 5}},
        "new": NONE,
        "other": {"mood": None, "energy": {"mean": 2.0, "n": 10}, "effort": {"mean": 3.0, "n": 10}},
    }
    assert storage.check_in_trends.calls == [(me, "mysuru", date(2025, 12, 1), date(2026, 11, 11))]


def test_the_openapi_contract(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    get = spec["paths"][URL]["get"]
    schemas = spec["components"]["schemas"]

    assert set(get["responses"]) >= {"200", "401", "503"}
    out = schemas["CheckInTrendsOut"]
    assert set(out["properties"]) == {
        "from",
        "to",
        "total",
        "enough",
        "min_total",
        "min_bucket",
        "months",
        "weekdays",
        "moon",
    }
    assert set(out["required"]) == set(out["properties"])
    assert set(schemas["AvgOut"]["properties"]) == {"mean", "n"}
    # Aggregates only: no date of a practice, no tags, nothing sealed. Each schema has its own
    # name (a second `MoonOut` would rename the stats one in the generated client).
    mine = ("CheckInTrendsOut", "AvgOut", "ScalesOut", "TrendsMonthOut", "TrendsMoonOut")
    assert set(mine) <= set(schemas)
    assert not [name for name in schemas if "__" in name]
    text = json.dumps({name: schemas[name] for name in mine})
    assert "tags" not in text
    assert "sealed" not in text


def test_weekdays_are_seven_monday_first(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    monday = date(2026, 8, 3)
    days = [ScaleDay(monday + timedelta(days=7 * i), None, 2, None) for i in range(6)]
    days += [ScaleDay(monday + timedelta(days=7 * i + 3), None, 5, None) for i in range(5)]
    storage.check_in_trends.by_account[me] = TrendFacts(tuple(days), ())

    weekdays = _get(api)["weekdays"]

    assert len(weekdays) == 7
    assert weekdays[0] == {"mood": None, "energy": {"mean": 2.0, "n": 6}, "effort": None}
    assert weekdays[3] == {"mood": None, "energy": {"mean": 5.0, "n": 5}, "effort": None}
    assert weekdays[6] == NONE
