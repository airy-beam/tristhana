"""UI-06 stage 2 `GET /api/v1/me/next-steps` (spec §6, §10): 401 without auth; a new person
gets `[]`; the payload shape and the offer order; each step gone once the caller's own data
answers it (a logged day, the reminder's "no", a set position, all through the API); only
the caller's own facts; 503 when storage is down; the OpenAPI contract. Real use case over the
in-memory storage, a frozen clock."""

import json
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FixedClock, InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.journey import JourneyFacts, NextStep, OwnedShala
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ME_TG, OTHER_TG = 42, 43
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
TODAY = date(2026, 11, 16)
URL = "/api/v1/me/next-steps"
SHALA, OTHER_SHALA = UUID(int=31), UUID(int=32)


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


def _account(api: TestClient, storage: InMemoryStorage, user_id: int = ME_TG) -> UUID:
    assert api.get("/api/v1/me", headers=_auth(user_id)).status_code == 200
    return storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(user_id))]


def _steps(api: TestClient, user_id: int = ME_TG) -> list[dict[str, object]]:
    found = api.get(URL, headers=_auth(user_id))
    assert found.status_code == 200, found.text
    body = found.json()
    assert set(body) == {"steps"}
    return body["steps"]


def _kinds(api: TestClient, user_id: int = ME_TG) -> list[object]:
    return [s["kind"] for s in _steps(api, user_id)]


def _log_today(api: TestClient, user_id: int = ME_TG) -> None:
    today = api.get("/api/v1/me/days", headers=_auth(user_id)).json()["today"]
    put = api.put(f"/api/v1/me/days/{today}", json={"status": "practiced"}, headers=_auth(user_id))
    assert put.status_code == 200, put.text


def test_next_steps_need_auth(api: TestClient) -> None:
    missing = api.get(URL)

    assert missing.status_code == 401
    assert missing.json() == {"code": "auth_missing"}


def test_a_new_person_has_no_step(api: TestClient) -> None:
    found = api.get(URL, headers=_auth())

    assert found.status_code == 200, found.text
    assert found.json() == {"steps": []}


def test_the_payload_shape_and_the_offer_order(api: TestClient, storage: InMemoryStorage) -> None:
    me = _account(api, storage)
    storage.repo.journey[me] = JourneyFacts(
        has_days=True,
        owned=(
            OwnedShala(SHALA, classes=1, students=0),
            OwnedShala(OTHER_SHALA, classes=0, students=0),
        ),
    )

    assert api.get(URL, headers=_auth()).json() == {
        "steps": [
            {"kind": "add_class", "shala_id": str(OTHER_SHALA)},
            {"kind": "invite_shala_students", "shala_id": str(SHALA)},
            {"kind": "reminder", "shala_id": None},
            {"kind": "position", "shala_id": None},
        ]
    }


def test_a_fresh_invite_link_offers_the_first_student(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _account(api, storage)
    storage.repo.journey[me] = JourneyFacts(invite_made_on=TODAY - timedelta(days=30))

    assert _steps(api) == [{"kind": "invite_student", "shala_id": None}]

    storage.repo.journey[me] = JourneyFacts(invite_made_on=TODAY - timedelta(days=32))

    assert _steps(api) == []


def test_each_step_goes_once_the_callers_data_answers_it(api: TestClient) -> None:
    """Derived on every read, through the same endpoints the app writes with."""
    assert _kinds(api) == []

    _log_today(api)
    assert _kinds(api) == ["reminder", "position"]

    # "No" answers the reminder as well as "yes" would.
    settings = "/api/v1/me/notification-settings"
    answered = api.patch(settings, json={"practice": {"on": False}}, headers=_auth())
    assert answered.status_code == 200, answered.text
    assert _kinds(api) == ["position"]

    event = {"kind": "set", "series": None, "last": None, "expected_event_id": None}
    started = api.post("/api/v1/me/progression/events", json=event, headers=_auth())
    assert started.status_code == 201, started.text
    assert _kinds(api) == []


def test_a_moon_setting_does_not_answer_the_reminder(api: TestClient) -> None:
    _log_today(api)
    settings = "/api/v1/me/notification-settings"
    assert api.patch(settings, json={"daily_cap": 2}, headers=_auth()).status_code == 200

    assert _kinds(api) == ["reminder", "position"]


def test_the_steps_are_the_callers_own(api: TestClient, storage: InMemoryStorage) -> None:
    me = _account(api, storage)
    other = _account(api, storage, OTHER_TG)
    _log_today(api, OTHER_TG)
    storage.repo.journey[other] = JourneyFacts(
        invite_made_on=TODAY, owned=(OwnedShala(OTHER_SHALA, classes=0, students=0),)
    )

    assert _steps(api) == []
    assert storage.repo.journey_reads == [me]
    assert _steps(api, OTHER_TG) == [
        {"kind": "add_class", "shala_id": str(OTHER_SHALA)},
        {"kind": "reminder", "shala_id": None},
        {"kind": "position", "shala_id": None},
    ]
    assert storage.repo.journey_reads == [me, other]


def test_there_is_no_way_to_ask_for_somebody_else(
    api: TestClient, storage: InMemoryStorage
) -> None:
    other = _account(api, storage, OTHER_TG)
    storage.repo.journey[other] = JourneyFacts(has_days=True)

    asked = api.get(URL, params={"account_id": str(other)}, headers=_auth())

    assert asked.json() == {"steps": []}
    assert api.get(f"{URL}/{other}", headers=_auth()).status_code == 404
    assert other not in storage.repo.journey_reads


def test_nothing_is_written(api: TestClient, storage: InMemoryStorage) -> None:
    """No dismissal flag (Q333): "Not now" stays on the device, so there is no write here."""
    _account(api, storage)
    _steps(api)  # the daily `last_seen_at` refresh of any authenticated call happens here
    before = storage.repo.writes

    for _ in range(3):
        _steps(api)

    assert storage.repo.writes == before
    for method in ("post", "put", "patch", "delete"):
        assert api.request(method, URL, headers=_auth()).status_code == 405


def test_database_down_is_503(api: TestClient, storage: InMemoryStorage) -> None:
    _account(api, storage)
    storage.repo.down = True

    found = api.get(URL, headers=_auth())

    assert found.status_code == 503
    assert found.json() == {"code": "unavailable"}


def test_the_contract_is_in_openapi(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    path = spec["paths"][URL]
    op = path["get"]

    assert set(path) == {"get"}
    assert op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/NextStepsOut"
    )
    assert {"401", "503"} <= set(op["responses"])
    assert "parameters" not in op
    schemas = spec["components"]["schemas"]
    steps = schemas["NextStepsOut"]
    assert steps["required"] == ["steps"]
    assert steps["properties"]["steps"]["items"]["$ref"].endswith("/NextStepOut")
    step = schemas["NextStepOut"]
    assert set(step["properties"]) == {"kind", "shala_id"}
    assert sorted(step["required"]) == ["kind", "shala_id"]
    assert step["properties"]["kind"]["enum"] == [n.value for n in NextStep]
    assert step["properties"]["kind"]["enum"] == [
        "add_class",
        "invite_shala_students",
        "invite_student",
        "reminder",
        "position",
    ]
    assert step["properties"]["shala_id"]["anyOf"] == [
        {"type": "string", "format": "uuid"},
        {"type": "null"},
    ]
