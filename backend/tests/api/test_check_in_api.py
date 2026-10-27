"""Check-in endpoints (PR-06, spec §4): PUT/DELETE per slot, `check_ins` on /me/days,
`offer_check_in` on /me, the tag list on /catalog, and the OpenAPI contract."""

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
TAGS = [
    "stiff",
    "open",
    "strong",
    "light",
    "heavy",
    "sore",
    "focused",
    "calm",
    "scattered",
    "steady_breath",
]
FULL = {"mood": 4, "energy": 3, "effort": 5, "tags": ["light", "calm"]}


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


def _day(status: str, api: TestClient, day: str | None = None, user_id: int = 42) -> str:
    day = day or _today()
    put = api.put(f"/api/v1/me/days/{day}", json={"status": status}, headers=_auth(user_id))
    assert put.status_code == 200
    return day


def _url(day: str, slot: int = 1) -> str:
    return f"/api/v1/me/days/{day}/check-ins/{slot}"


def _put(api: TestClient, day: str, body: dict[str, Any], user_id: int = 42) -> Any:
    return api.put(_url(day), json=body, headers=_auth(user_id))


def _days(api: TestClient, user_id: int = 42) -> list[dict[str, Any]]:
    return api.get("/api/v1/me/days", headers=_auth(user_id)).json()["days"]


def _out(body: dict[str, Any]) -> dict[str, Any]:
    """Tags compared as a set: their order on the wire is the server's."""
    return body | {"tags": sorted(body["tags"])}


# PUT / DELETE


def test_check_in_endpoints_need_auth(api: TestClient) -> None:
    assert api.put(_url(_today()), json=FULL).status_code == 401
    assert api.delete(_url(_today())).status_code == 401


def test_put_round_trip_and_days_include_it(api: TestClient) -> None:
    day = _day("practiced", api)

    saved = _put(api, day, FULL)
    [logged] = _days(api)

    assert saved.status_code == 200
    assert _out(saved.json()) == _out(FULL | {"slot": 1})
    assert [_out(c) for c in logged["check_ins"]] == [_out(saved.json())]
    assert logged["practices"] == []  # a check-in needs no details


def test_put_replaces_all_fields(api: TestClient) -> None:
    day = _day("practiced", api)
    _put(api, day, FULL)

    saved = _put(api, day, {"energy": 2})

    assert saved.json() == {"slot": 1, "mood": None, "energy": 2, "effort": None, "tags": []}


def test_tags_come_back_in_display_order(api: TestClient) -> None:
    day = _day("practiced", api)

    saved = _put(api, day, {"tags": ["steady_breath", "stiff", "calm"]})

    assert saved.json()["tags"] == ["stiff", "calm", "steady_breath"]


def test_an_all_empty_put_reads_back_as_none(api: TestClient) -> None:
    day = _day("practiced", api)

    saved = _put(api, day, {"mood": None, "energy": None, "effort": None, "tags": []})

    assert saved.status_code == 200
    assert [d["check_ins"] for d in _days(api)] == [[]]


@pytest.mark.parametrize("status", ["rest", "moon", "ladies", "sick", "travel", "skipped"])
def test_put_needs_a_practiced_day(api: TestClient, status: str) -> None:
    day = _day(status, api)

    response = _put(api, day, FULL)

    assert (response.status_code, response.json()) == (409, {"code": "day_not_practiced"})


def test_put_on_a_day_never_logged_is_409(api: TestClient) -> None:
    response = _put(api, _today(), FULL)

    assert (response.status_code, response.json()) == (409, {"code": "day_not_practiced"})


@pytest.mark.parametrize(
    "body",
    [
        {"mood": 6},
        {"energy": 0},
        {"effort": 10},
        {"mood": "4"},
        {"tags": ["sleepy"]},  # unknown: an enum error
        {"tags": ["calm", "pain"]},
    ],
)
def test_put_rejects_invalid_values(api: TestClient, body: dict[str, Any]) -> None:
    day = _day("practiced", api)

    response = _put(api, day, body)

    assert response.status_code == 422
    code = response.json().get("code")
    assert code in (None, "invalid_check_in")  # None: pydantic's own validation error
    assert [d["check_ins"] for d in _days(api)] == [[]]


def test_only_slot_one_for_now(api: TestClient) -> None:
    day = _day("practiced", api)

    put = api.put(_url(day, slot=2), json=FULL, headers=_auth())
    delete = api.delete(_url(day, slot=2), headers=_auth())

    assert (put.status_code, delete.status_code) == (422, 422)


def test_delete_is_idempotent(api: TestClient) -> None:
    day = _day("practiced", api)
    _put(api, day, FULL)

    first = api.delete(_url(day), headers=_auth())
    again = api.delete(_url(day), headers=_auth())

    assert (first.status_code, again.status_code) == (204, 204)
    assert [d["check_ins"] for d in _days(api)] == [[]]
    assert [d["status"] for d in _days(api)] == ["practiced"]


def test_a_status_change_drops_the_check_in(api: TestClient) -> None:
    day = _day("practiced", api)
    _put(api, day, FULL)

    _day("rest", api, day)
    _day("practiced", api, day)

    assert [d["check_ins"] for d in _days(api)] == [[]]


def test_remove_details_keeps_the_check_in(api: TestClient) -> None:
    day = _day("practiced", api)
    api.put(f"/api/v1/me/days/{day}/practices/1", json={"duration_min": 90}, headers=_auth())
    _put(api, day, FULL)

    api.delete(f"/api/v1/me/days/{day}/practices/1", headers=_auth())

    [logged] = _days(api)
    assert logged["practices"] == []
    assert [c["mood"] for c in logged["check_ins"]] == [4]


def test_check_ins_are_private_to_their_owner(api: TestClient) -> None:
    day = _day("practiced", api, user_id=42)
    _day("practiced", api, day, user_id=43)
    _put(api, day, FULL, user_id=42)

    assert [d["check_ins"] for d in _days(api, user_id=43)] == [[]]


def test_days_carry_an_empty_list_on_other_days(api: TestClient) -> None:
    yesterday = (datetime.fromisoformat(_today()) - timedelta(days=1)).date().isoformat()
    _day("rest", api, yesterday)
    _put(api, _day("practiced", api), FULL)

    days = _days(api)

    assert [(d["status"], len(d["check_ins"])) for d in days] == [("rest", 0), ("practiced", 1)]


# The setting on /me


def test_offer_check_in_is_on_until_chosen_and_null_means_the_default(api: TestClient) -> None:
    assert api.get("/api/v1/me", headers=_auth()).json()["offer_check_in"] is True

    off = api.patch("/api/v1/me", json={"offer_check_in": False}, headers=_auth()).json()
    renamed = api.patch("/api/v1/me", json={"display_name": "Ash"}, headers=_auth()).json()
    back = api.patch("/api/v1/me", json={"offer_check_in": None}, headers=_auth()).json()
    on = api.patch("/api/v1/me", json={"offer_check_in": True}, headers=_auth()).json()

    assert off["offer_check_in"] is False
    assert renamed["offer_check_in"] is False  # omitted = unchanged
    assert back["offer_check_in"] is True
    assert on["offer_check_in"] is True
    assert api.get("/api/v1/me", headers=_auth()).json()["offer_check_in"] is True


def test_turning_the_offer_off_never_blocks_a_check_in(api: TestClient) -> None:
    api.patch("/api/v1/me", json={"offer_check_in": False}, headers=_auth())
    day = _day("practiced", api)

    assert _put(api, day, FULL).status_code == 200


# The catalog


def test_catalog_lists_the_tags_in_display_order_with_their_group(api: TestClient) -> None:
    body = api.get("/api/v1/catalog").json()

    assert body["check_in_tags"] == [
        {"key": key, "group": "body" if i < 6 else "mind"} for i, key in enumerate(TAGS)
    ]


def test_catalog_etag_covers_the_tags(api: TestClient) -> None:
    from tristhana.api.v1.practice import catalog_etag

    first = api.get("/api/v1/catalog")
    version = first.json()["version"]

    assert first.headers["etag"] == catalog_etag(version, TAGS)
    assert catalog_etag(version, TAGS) == catalog_etag(version, list(TAGS))  # stable
    assert catalog_etag(version, TAGS[:-1]) != catalog_etag(version, TAGS)  # a tag removed
    assert catalog_etag(version, [*TAGS, "sleepy"]) != catalog_etag(version, TAGS)  # added
    assert catalog_etag(version, TAGS[::-1]) != catalog_etag(version, TAGS)  # reordered
    assert catalog_etag(f"{version}x", TAGS) != catalog_etag(version, TAGS)
    cached = api.get("/api/v1/catalog", headers={"If-None-Match": first.headers["etag"]})
    stale = api.get("/api/v1/catalog", headers={"If-None-Match": f'"{version}"'})
    assert (cached.status_code, stale.status_code) == (304, 200)


# OpenAPI


def test_openapi_has_the_paths_the_enum_and_the_error_code(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()
    schemas = schema["components"]["schemas"]

    assert "invalid_check_in" in schemas["ErrorCode"]["enum"]
    assert schemas["CheckInTag"]["enum"] == TAGS
    assert "/api/v1/me/days/{date}/check-ins/{slot}" in schema["paths"]
    assert {"put", "delete"} <= set(schema["paths"]["/api/v1/me/days/{date}/check-ins/{slot}"])
    assert set(schemas["CheckInOut"]["properties"]) == {"slot", "mood", "energy", "effort", "tags"}
    assert "check_ins" in schemas["Day"]["properties"]
    assert "offer_check_in" in schemas["Me"]["properties"]
    assert "offer_check_in" in schemas["MePatch"]["properties"]
    assert "check_in_tags" in schemas["CatalogOut"]["properties"]
