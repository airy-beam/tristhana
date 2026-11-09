"""GM-02 `GET /api/v1/me/badges` (spec §5, §9): 401 without auth; an empty account gets `[]`;
the payload shape, earned only and in file order; the OpenAPI contract. Real use case over an
in-memory facts fake, a frozen clock."""

import json
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.badge_fakes import InMemoryBadgeFacts
from tests.fakes import FixedClock, InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.badges import BadgeFacts
from tristhana.domain.days import DayStatus
from tristhana.domain.progression import EventKind, Position, ProgressionEvent
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ME_TG = 42
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
URL = "/api/v1/me/badges"
FIELDS = {
    "key",
    "group",
    "icon",
    "earned_on",
    "at_record_start",
    "count",
    "days",
    "before",
    "series",
    "stop",
    "item",
}


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


def test_badges_need_auth(api: TestClient) -> None:
    assert api.get(URL).status_code == 401


def test_an_empty_account_has_no_badges(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)

    found = api.get(URL, headers=_auth())

    assert found.status_code == 200, found.text
    assert found.json() == {"badges": []}


def test_the_payload_is_earned_only_in_file_order(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    first = date(2026, 1, 1)
    logged = {first + timedelta(days=i): DayStatus.PRACTICED for i in range(9)}
    start = ProgressionEvent(1, EventKind.START, first, after=Position("intermediate", "pasasana"))
    facts: InMemoryBadgeFacts = storage.badges
    facts.by_account[me] = BadgeFacts(logged=logged, kept_counts=frozenset({100}), events=(start,))

    body = api.get(URL, headers=_auth()).json()["badges"]

    assert all(set(b) == FIELDS for b in body)
    assert [b["key"] for b in body] == [
        "ekam",
        "nava",
        "shatam",
        "yoga-chikitsa",
        "nadi-shodhana",
        "supta-kurmasana",
    ]
    by = {b["key"]: b for b in body}
    assert by["nava"] | {"icon": None} == {
        "key": "nava",
        "group": "practice",
        "icon": None,
        "earned_on": "2026-01-09",
        "at_record_start": False,
        "count": 9,
        "days": None,
        "before": None,
        "series": None,
        "stop": None,
        "item": None,
    }
    assert (by["shatam"]["earned_on"], by["shatam"]["count"]) == (None, 100)
    assert by["nadi-shodhana"] | {"icon": None} == {
        "key": "nadi-shodhana",
        "group": "asanas",
        "icon": None,
        "earned_on": "2026-01-01",
        "at_record_start": True,
        "count": None,
        "days": None,
        "before": None,
        "series": "intermediate",
        "stop": None,
        "item": None,
    }
    assert (by["supta-kurmasana"]["series"], by["supta-kurmasana"]["stop"]) == (
        "primary",
        "supta-kurmasana",
    )


def test_before_is_hh_mm(api: TestClient, storage: InMemoryStorage) -> None:
    from datetime import time as wall

    me = _me(api, storage)
    first = date(2026, 1, 1)
    starts = tuple((first + timedelta(days=i), wall(5, 0)) for i in range(10))
    facts: InMemoryBadgeFacts = storage.badges
    logged = {on: DayStatus.PRACTICED for on, _ in starts}
    facts.by_account[me] = BadgeFacts(logged=logged, starts=starts)

    body = api.get(URL, headers=_auth()).json()["badges"]

    dawn = [(b["key"], b["before"], b["count"]) for b in body if b["key"] == "before-dawn"]
    assert dawn == [("before-dawn", "06:00", 10)]


def test_the_contract_is_in_openapi(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    op = spec["paths"][URL]["get"]

    assert op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/BadgesOut"
    )
    badge = spec["components"]["schemas"]["BadgeOut"]
    assert set(badge["properties"]) == FIELDS
    assert badge["properties"]["group"]["enum"] == ["practice", "asanas"]
