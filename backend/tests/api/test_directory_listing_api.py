"""ID-05 routes (spec §7; ADR-0042): `GET/PUT/DELETE /api/v1/me/directory-listing` and the
`listing` field on `GET /api/v1/me/links`. initData (401 without), `no-store`, the exact key
sets, 422 `invalid_listing`, 409 `listing_wait`, DELETE idempotent, 503 with no admin
configured; there is no admin endpoint. Real use cases over the in-memory ports."""

import json
import time as wall
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.directory_listing_fakes import always
from tests.fakes import FakeNotifier, InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.api.initdata import sign
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.directory_listing import ListingStatus, Outcome, Step, clean
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ME_TG = 42
NOW = datetime(2026, 11, 11, 10, 30, tzinfo=UTC)
URL = "/api/v1/me/directory-listing"
KEYS = {
    "status",
    "name_as_listed",
    "region",
    "declared_level",
    "note",
    "requested_at",
    "checked_on",
    "can_send",
    "available",
}
BODY = {
    "name_as_listed": "Anna Petrova",
    "region": "Russia",
    "declared_level": "authorised-2",
    "note": "anna.example is in the directory",
}


class Frozen:
    instant = NOW

    def now(self) -> datetime:
        return Frozen.instant


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
def notifier() -> FakeNotifier:
    return FakeNotifier()


def _client(
    storage: InMemoryStorage,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
    admins: str,
) -> TestClient:
    import tristhana.main

    Frozen.instant = NOW
    monkeypatch.setattr(tristhana.main, "SystemClock", Frozen)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        platform_admin_ids=admins,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings, storage, notifier))


@pytest.fixture
def admin(storage: InMemoryStorage) -> UUID:
    return person(storage, "9001", "Admin").id


@pytest.fixture
def api(
    storage: InMemoryStorage,
    notifier: FakeNotifier,
    admin: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    with _client(storage, notifier, monkeypatch, str(admin)) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage) -> UUID:
    assert api.get("/api/v1/me", headers=_auth()).status_code == 200
    return storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(ME_TG))]


async def _decide(storage: InMemoryStorage, me: UUID, admin: UUID, outcome: Outcome) -> None:
    row = storage.listings.rows[me]
    await storage.listings.decide(me, row.revision, outcome, date(2026, 11, 11), admin)


def test_every_route_needs_init_data(api: TestClient) -> None:
    assert api.get(URL).status_code == 401
    assert api.put(URL, json=BODY).status_code == 401
    assert api.delete(URL).status_code == 401


def test_get_with_no_request_is_none(api: TestClient) -> None:
    response = api.get(URL, headers=_auth())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    out = response.json()
    assert set(out) == KEYS
    assert out == {
        "status": "none",
        "name_as_listed": None,
        "region": None,
        "declared_level": None,
        "note": None,
        "requested_at": None,
        "checked_on": None,
        "can_send": True,
        "available": True,
    }


def test_put_sends_a_request_and_tells_the_admin(api: TestClient, notifier: FakeNotifier) -> None:
    response = api.put(URL, json=BODY, headers=_auth())
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    out = response.json()
    assert set(out) == KEYS
    assert (out["status"], out["name_as_listed"], out["region"]) == (
        "pending",
        "Anna Petrova",
        "Russia",
    )
    assert (out["declared_level"], out["note"]) == ("authorised-2", BODY["note"])
    assert out["checked_on"] is None
    assert [r.telegram_id for r in notifier.listing_requests] == ["9001"]
    assert api.get(URL, headers=_auth()).json()["status"] == "pending"


def test_put_cleans_the_text(api: TestClient) -> None:
    body = BODY | {"name_as_listed": "  Anna \t Petrova ", "note": "  "}
    out = api.put(URL, json=body, headers=_auth()).json()
    assert (out["name_as_listed"], out["note"]) == ("Anna Petrova", None)


@pytest.mark.parametrize(
    "change",
    [
        {"name_as_listed": ""},
        {"name_as_listed": "a" * 101},
        {"region": "  "},
        {"region": "r" * 61},
        {"declared_level": "level-3"},
        {"note": "n" * 301},
    ],
)
def test_put_refuses_invalid_details(
    api: TestClient, storage: InMemoryStorage, change: dict[str, Any]
) -> None:
    response = api.put(URL, json=BODY | change, headers=_auth())
    assert response.status_code == 422, response.text
    assert response.json() == {"code": "invalid_listing"}
    assert storage.listings.rows == {}


def test_a_validation_error_never_echoes_what_was_sent(api: TestClient) -> None:
    response = api.put(URL, json=BODY | {"name_as_listed": "S" * 500}, headers=_auth())
    assert response.status_code == 422
    assert "SSSS" not in response.text


def test_editing_a_waiting_request_tells_no_one(api: TestClient, notifier: FakeNotifier) -> None:
    api.put(URL, json=BODY, headers=_auth())
    out = api.put(URL, json=BODY | {"region": "Kazakhstan"}, headers=_auth()).json()
    assert (out["status"], out["region"]) == ("pending", "Kazakhstan")
    assert len(notifier.listing_requests) == 1


async def test_sending_again_within_a_day_is_409(
    api: TestClient, storage: InMemoryStorage, admin: UUID
) -> None:
    me = _me(api, storage)
    api.put(URL, json=BODY, headers=_auth())
    await _decide(storage, me, admin, Outcome.NOT_FOUND)
    out = api.get(URL, headers=_auth()).json()
    assert (out["status"], out["can_send"], out["note"]) == ("not_found", False, None)
    response = api.put(URL, json=BODY, headers=_auth())
    assert response.status_code == 409
    assert response.json() == {"code": "listing_wait"}
    Frozen.instant = NOW + timedelta(hours=24)
    assert api.get(URL, headers=_auth()).json()["can_send"] is True
    assert api.put(URL, json=BODY, headers=_auth()).json()["status"] == "pending"


async def test_a_listed_level_change_stays_listed(
    api: TestClient, storage: InMemoryStorage, admin: UUID, notifier: FakeNotifier
) -> None:
    me = _me(api, storage)
    api.put(URL, json=BODY, headers=_auth())
    await _decide(storage, me, admin, Outcome.LISTED)
    out = api.put(URL, json=BODY | {"declared_level": None}, headers=_auth()).json()
    assert (out["status"], out["declared_level"], out["checked_on"]) == (
        "listed",
        None,
        "2026-11-11",
    )
    assert len(notifier.listing_requests) == 1


def test_delete_clears_the_details_and_is_idempotent(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    assert api.delete(URL, headers=_auth()).status_code == 204  # nothing to remove
    assert me not in storage.listings.rows
    api.put(URL, json=BODY, headers=_auth())
    response = api.delete(URL, headers=_auth())
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert api.delete(URL, headers=_auth()).status_code == 204
    out = api.get(URL, headers=_auth()).json()
    assert (out["status"], out["name_as_listed"], out["region"], out["note"]) == (
        "withdrawn",
        None,
        None,
        None,
    )
    assert storage.listings.rows[me].status is ListingStatus.WITHDRAWN


def test_no_admin_configured_takes_no_requests_and_says_so_on_a_200(
    storage: InMemoryStorage, notifier: FakeNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client(storage, notifier, monkeypatch, "") as api:
        found = api.get(URL, headers=_auth())
        assert found.status_code == 200  # a flag, not a 5xx: off is not an outage
        assert (found.json()["status"], found.json()["available"]) == ("none", False)
        refused = api.put(URL, json=BODY, headers=_auth())
        assert refused.status_code == 503
        assert refused.json() == {"code": "unavailable"}
        assert api.delete(URL, headers=_auth()).status_code == 204
    assert storage.listings.rows == {}


async def test_a_line_can_still_be_removed_after_the_admins_are_gone(
    storage: InMemoryStorage, notifier: FakeNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--set-env-vars` replaces every variable on a deploy: if the admin list is ever
    dropped, lines keep showing, so their owners must still be able to take them down."""
    admin = person(storage, "9001", "Admin").id
    with _client(storage, notifier, monkeypatch, "") as api:
        me = _me(api, storage)
        details = clean("Anna Petrova", "Russia", None, None)
        await storage.listings.save(me, details, always(Step.SEND), NOW)
        await _decide(storage, me, admin, Outcome.LISTED)
        found = api.get(URL, headers=_auth()).json()
        assert (found["status"], found["available"]) == ("listed", False)
        assert api.delete(URL, headers=_auth()).status_code == 204
        assert api.get(URL, headers=_auth()).json()["status"] == "withdrawn"
    assert storage.listings.rows[me].status is ListingStatus.WITHDRAWN


async def test_links_carry_the_line_for_a_listed_teacher_only(
    api: TestClient, storage: InMemoryStorage, admin: UUID
) -> None:
    me = _me(api, storage)
    anna = person(storage, "1001", "Anna")
    boris = person(storage, "1002", "Boris")
    student = person(storage, "1003", "Clara")
    for teacher in (anna, boris):
        storage.teacher_links.add(me, teacher.id)
    storage.teacher_links.add(student.id, me)
    details = clean("Anna Petrova", "Russia", "authorised-2", None)
    await storage.listings.save(anna.id, details, always(Step.SEND), NOW)
    await _decide(storage, anna.id, admin, Outcome.LISTED)
    out = api.get("/api/v1/me/links", headers=_auth()).json()
    by_name = {t["name"]: t for t in out["teachers"]}
    assert by_name["Anna"]["listing"] == {
        "name_as_listed": "Anna Petrova",
        "checked_on": "2026-11-11",
        "declared_level": "authorised-2",
    }
    assert by_name["Boris"]["listing"] is None
    assert all("listing" not in s for s in out["students"])


def test_there_is_no_admin_endpoint_and_the_spec_lists_the_codes(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    paths = [p for p in spec["paths"] if "listing" in p or "admin" in p]
    assert paths == ["/api/v1/me/directory-listing"]
    codes = json.dumps(spec["components"]["schemas"])
    assert "listing_wait" in codes
    assert "invalid_listing" in codes
