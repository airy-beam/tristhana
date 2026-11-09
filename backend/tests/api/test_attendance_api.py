"""Attendance endpoints (SC-05 spec §4): auth; exact shapes; 404 vs 403 vs 409 vs 422;
`attendance_counts` null for students on the shala schedule; `attendance` and `can_claim` on
My schedule rows; `limit` > 50 → 422; `no-store`. A frozen clock (Mon 9 Nov 2026, 08:00
Almaty)."""

import json
import time as wall
from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.api.initdata import sign
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.classes import ClassType
from tristhana.domain.shalas import ShalaRole
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
MON, SUN = date(2026, 11, 9), date(2026, 11, 8)
EVERY_DAY = frozenset(range(1, 8))
ROSTER_KEYS = {
    "shala_id", "shala_name", "occurrence", "attendable", "confirmed", "claimed", "people",
    "more",
}  # fmt: skip
ROSTER_OCCURRENCE_KEYS = {
    "key", "on", "start", "end", "starts_at", "zone", "city", "type", "title", "cancelled",
}  # fmt: skip
PERSON_KEYS = {"account_id", "name", "state", "staff"}


def _auth(user_id: int = ME_TG, name: str = "Ash") -> dict[str, str]:
    profile = {"id": user_id, "first_name": name, "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(wall.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    storage = shala_storage()
    storage.repo.clock.instant = NOW
    return storage


@pytest.fixture
def api(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    import tristhana.main

    class Frozen:
        def now(self) -> datetime:
            return NOW

    monkeypatch.setattr(tristhana.main, "SystemClock", Frozen)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage) -> UUID:
    assert api.get("/api/v1/me", headers=_auth()).status_code == 200
    me = storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(ME_TG))]
    from dataclasses import replace

    storage.repo.accounts[me] = replace(storage.repo.accounts[me], timezone="Asia/Almaty")
    return me


def _world(storage: InMemoryStorage, me: UUID, role: str | None) -> tuple[UUID, UUID, UUID]:
    """Anna's shala with a daily Mysore; me as `role` (None: student; "nobody"); Vera a
    student. Returns (shala, class, vera)."""
    anna = person(storage, "1001", "Anna")
    vera = person(storage, "1002", "Vera")
    shala = storage.shalas.add_shala(anna.id).id
    storage.shalas.add_student(shala, vera.id)
    if role is None:
        storage.shalas.add_student(shala, me)
    elif role != "nobody":
        storage.shalas.add_staff(shala, me, ShalaRole(role))
    cls = storage.schedule.add_class(shala, weekdays=EVERY_DAY, starts_on=date(2026, 10, 1))
    storage.attendance  # attaches the fake to the schedule  # noqa: B018
    return shala, cls.id, vera.id


def _roster_url(shala: UUID, cls: UUID, key: date = MON) -> str:
    return f"/api/v1/shalas/{shala}/classes/{cls}/occurrences/{key}/attendance"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", f"/api/v1/me/attendance/{uuid4()}/2026-11-09"),
        ("DELETE", f"/api/v1/me/attendance/{uuid4()}/2026-11-09"),
        ("GET", _roster_url(uuid4(), uuid4())),
        ("PATCH", _roster_url(uuid4(), uuid4())),
    ],
)
def test_every_route_needs_auth(api: TestClient, method: str, path: str) -> None:
    response = api.request(method, path, json={} if method == "PATCH" else None)
    assert (response.status_code, response.json()) == (401, {"code": "auth_missing"})


def test_a_student_claims_and_removes(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    _, cls, _ = _world(storage, me, None)
    url = f"/api/v1/me/attendance/{cls}/{MON}"

    response = api.put(url, headers=_auth())

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "class_id": str(cls), "key": "2026-11-09", "state": "claimed", "day": "2026-11-09",
        "log_day": True,
    }  # fmt: skip
    mine = api.get("/api/v1/me/schedule", params={"from": "2026-11-08", "days": 3},
                   headers=_auth()).json()  # fmt: skip
    rows = {r["on"]: r for r in mine["occurrences"]}
    assert rows["2026-11-09"]["attendance"] == "claimed"
    assert rows["2026-11-09"]["can_claim"]
    assert rows["2026-11-08"]["attendance"] is None
    assert rows["2026-11-08"]["can_claim"]
    assert not rows["2026-11-10"]["can_claim"]
    assert rows["2026-11-09"]["attendance_counts"] is None  # a student sees no counts

    assert api.delete(url, headers=_auth()).status_code == 204
    assert api.delete(url, headers=_auth()).status_code == 204  # idempotent
    assert storage.attendance.rows == {}


def test_claim_errors(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    _, cls, _ = _world(storage, me, "nobody")
    assert api.put(f"/api/v1/me/attendance/{cls}/{MON}", headers=_auth()).json() == {
        "code": "not_found"
    }
    storage.shalas.add_student(storage.schedule.classes[cls][0], me)
    future = api.put(f"/api/v1/me/attendance/{cls}/2026-11-10", headers=_auth())
    assert (future.status_code, future.json()) == (409, {"code": "not_attendable"})
    old = api.put(f"/api/v1/me/attendance/{cls}/2026-11-02", headers=_auth())
    assert old.status_code == 409


def test_conference_offers_no_log_day(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala, _, _ = _world(storage, me, None)
    conf = storage.schedule.add_class(shala, weekdays=EVERY_DAY, type=ClassType.CONFERENCE,
                                      start=time(7, 0), minutes=60)  # fmt: skip
    body = api.put(f"/api/v1/me/attendance/{conf.id}/{MON}", headers=_auth()).json()
    assert body["log_day"] is False


def test_staff_roster_and_deltas(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala, cls, vera = _world(storage, me, "assistant")

    response = api.get(_roster_url(shala, cls), headers=_auth())

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == ROSTER_KEYS
    assert set(body["occurrence"]) == ROSTER_OCCURRENCE_KEYS
    assert body["occurrence"]["zone"] == "Asia/Almaty"
    assert body["occurrence"]["start"] == "06:00"
    assert body["attendable"]
    assert (body["confirmed"], body["claimed"]) == (0, 0)
    assert [p["name"] for p in body["people"]] == ["Vera"]
    assert all(set(p) == PERSON_KEYS for p in body["people"])

    patched = api.patch(_roster_url(shala, cls), json={"present": [str(vera)]}, headers=_auth())
    assert (patched.status_code, patched.json()) == (200, {"confirmed": 1, "claimed": 0})
    schedule = api.get(f"/api/v1/shalas/{shala}/schedule", params={"from": "2026-11-09",
                       "days": 1}, headers=_auth()).json()  # fmt: skip
    assert schedule["occurrences"][0]["attendance_counts"] == {"confirmed": 1, "claimed": 0}

    absent = api.patch(_roster_url(shala, cls), json={"removed": [str(vera)]}, headers=_auth())
    assert absent.json() == {"confirmed": 0, "claimed": 0}


def test_staff_errors(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala, cls, vera = _world(storage, me, "office")
    both = {"present": [str(vera)], "removed": [str(vera)]}
    r = api.patch(_roster_url(shala, cls), json=both, headers=_auth())
    assert (r.status_code, r.json()) == (422, {"code": "invalid_attendance"})
    stranger = {"present": [str(uuid4())]}
    r = api.patch(_roster_url(shala, cls), json=stranger, headers=_auth())
    assert r.json() == {"code": "invalid_attendance"}
    too_many = {"present": [str(uuid4()) for _ in range(101)]}
    assert api.patch(_roster_url(shala, cls), json=too_many, headers=_auth()).status_code == 422
    r = api.patch(_roster_url(shala, cls, date(2026, 11, 10)), json={}, headers=_auth())
    assert (r.status_code, r.json()) == (409, {"code": "not_attendable"})
    r = api.get(_roster_url(uuid4(), cls), headers=_auth())
    assert (r.status_code, r.json()) == (404, {"code": "not_found"})
    r = api.get(_roster_url(shala, cls), params={"limit": 51}, headers=_auth())
    assert r.status_code == 422


def test_a_student_gets_403_on_the_roster(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala, cls, _ = _world(storage, me, None)
    for method in ("GET", "PATCH"):
        r = api.request(method, _roster_url(shala, cls), json={}, headers=_auth())
        assert (r.status_code, r.json()) == (403, {"code": "not_allowed"}), method
    schedule = api.get(f"/api/v1/shalas/{shala}/schedule", params={"from": "2026-11-09",
                       "days": 1}, headers=_auth()).json()  # fmt: skip
    assert schedule["occurrences"][0]["attendance_counts"] is None


def test_the_contract_is_in_openapi(api: TestClient) -> None:
    spec: dict[str, Any] = api.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/me/attendance/{class_id}/{key}" in paths
    roster = "/api/v1/shalas/{id}/classes/{class_id}/occurrences/{key}/attendance"
    assert {"get", "patch"} <= set(paths[roster])
    codes = json.dumps(spec["components"]["schemas"]["ErrorCode"])
    assert "not_attendable" in codes
    assert "invalid_attendance" in codes
