"""Progression endpoints (PR-08, spec §4): GET (unset with a suggestion, set with the
per-series view, next and later stops), POST events (set / given / items with
celebrations; 409 `progression_changed`; 422 cases), DELETE (undo, 409 `not_latest`), the
"Not new" dismissal, the practice PUT's `new_asana_hint`, "mine" presets, the catalog's
`milestone_items`, and the OpenAPI contract."""

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
URL = "/api/v1/me/progression"


def _auth(user_id: int = 42) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _today() -> date:
    return (datetime.now(UTC) + timedelta(hours=3)).date()  # provisional Moscow


def _get(api: TestClient) -> dict[str, Any]:
    found = api.get(URL, headers=_auth())
    assert found.status_code == 200
    return found.json()


def _post(api: TestClient, **body: Any) -> Any:
    return api.post(f"{URL}/events", json=body, headers=_auth())


def _set(api: TestClient, series: str | None, last: str | None) -> dict[str, Any]:
    expected = _get(api)["last_event_id"]
    done = _post(api, kind="set", series=series, last=last, expected_event_id=expected)
    assert done.status_code == 201
    return done.json()


def test_endpoints_need_auth(api: TestClient) -> None:
    assert api.get(URL).status_code == 401
    assert api.post(f"{URL}/events", json={}).status_code == 401
    assert api.delete(f"{URL}/events/1").status_code == 401
    assert api.post(f"{URL}/hint-dismissals", json={}).status_code == 401


def test_unset_has_no_position_and_suggests_from_the_log(api: TestClient) -> None:
    day = _today() - timedelta(days=1)
    api.put(f"/api/v1/me/days/{day}", json={"status": "practiced"}, headers=_auth())
    practice = {"context": "mysore", "length": {"series": ["primary"], "end": "navasana"}}
    api.put(f"/api/v1/me/days/{day}/practices/1", json=practice, headers=_auth())

    found = _get(api)

    assert found["set"] is False
    assert found["position"] is None
    assert found["suggested"] == {"series": "primary", "last": "navasana"}
    assert found["suggested_length"] == {
        "series": ["primary"],
        "end": "navasana",
        "first_part": None,
    }
    assert found["events"] == []
    assert found["last_event_id"] is None
    assert found["today"] == _today().isoformat()


def test_set_then_given_celebrates_and_lists_events(api: TestClient) -> None:
    started = _set(api, "primary", "urdhva-mukha-paschimottanasana")
    assert started["celebrations"] == []
    assert started["event"]["kind"] == "start"
    expected = started["progression"]["last_event_id"]

    given = _post(
        api, kind="given", series="primary", last="setu-bandhasana", expected_event_id=expected
    )

    assert given.status_code == 201
    body = given.json()
    assert [c["kind"] for c in body["celebrations"]] == ["new_asana", "series_complete"]
    assert body["celebrations"][0]["key"] == "setu-bandhasana"
    assert body["event"]["from"] == {"series": "primary", "last": "urdhva-mukha-paschimottanasana"}
    assert body["event"]["to"] == {"series": "primary", "last": "setu-bandhasana"}
    progression = body["progression"]
    assert progression["next"] == {"series": "intermediate", "last": "pasasana"}
    assert progression["length"] == {"series": ["primary"], "end": None, "first_part": None}
    assert progression["later"][0] == {"series": "intermediate", "last": "pasasana"}
    assert {s["slug"]: s["last"] for s in progression["by_series"]} == {
        "primary": "setu-bandhasana",
        "intermediate": None,
        "advanced-a": None,
        "advanced-b": None,
    }
    assert [e["kind"] for e in progression["events"]] == ["given", "start"]
    assert progression["events"][0]["marked_by_self"] is True
    assert _get(api)["events"] == progression["events"]


def test_items_and_standing_only(api: TestClient) -> None:
    started = _set(api, None, None)
    assert started["progression"]["position"] == {"series": None, "last": None}
    expected = started["progression"]["last_event_id"]
    item = _post(api, kind="item_given", item="drop-backs", expected_event_id=expected)
    assert item.status_code == 201
    assert item.json()["celebrations"] == [
        {"kind": "item", "series": None, "key": "drop-backs", "first": None, "count": None}
    ]
    assert item.json()["progression"]["items"] == ["drop-backs"]


def test_a_stale_expected_id_is_a_409(api: TestClient) -> None:
    started = _set(api, "primary", "navasana")
    stale = started["progression"]["last_event_id"]
    _set(api, "primary", "kurmasana")
    late = _post(
        api, kind="given", series="primary", last="supta-kurmasana", expected_event_id=stale
    )
    assert late.status_code == 409
    assert late.json() == {"code": "progression_changed"}


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "given", "series": "primary", "last": "marichyasana-a"},  # not forward
        {"kind": "set", "series": "primary", "last": "utthita-trikonasana-b"},  # not a stop
        {"kind": "item_given", "item": "vrksasana"},  # not a milestone
        {"kind": "item_given"},  # no item
    ],
)
def test_invalid_changes_are_422(api: TestClient, body: dict[str, Any]) -> None:
    started = _set(api, "primary", "navasana")
    expected = started["progression"]["last_event_id"]
    refused = _post(api, **body, expected_event_id=expected)
    assert refused.status_code == 422
    assert refused.json() == {"code": "invalid_progression"}


def test_given_before_set_and_bad_dates_are_422(api: TestClient) -> None:
    unset = _post(api, kind="given", series="primary", last="navasana", expected_event_id=None)
    assert unset.json() == {"code": "invalid_progression"}
    future = (_today() + timedelta(days=2)).isoformat()
    late = _post(
        api,
        kind="set",
        series="primary",
        last="navasana",
        occurred_on=future,
        expected_event_id=None,
    )
    assert late.status_code == 422
    assert late.json() == {"code": "date_in_future"}
    early = _post(
        api,
        kind="set",
        series="primary",
        last="navasana",
        occurred_on="1999-12-31",
        expected_event_id=None,
    )
    assert early.json() == {"code": "date_too_early"}


def test_undo_only_the_latest(api: TestClient) -> None:
    started = _set(api, "primary", "navasana")
    first = started["event"]["id"]
    changed = _set(api, "primary", "kurmasana")
    assert api.delete(f"{URL}/events/{first}", headers=_auth()).status_code == 409
    undone = api.delete(f"{URL}/events/{changed['event']['id']}", headers=_auth())
    assert undone.status_code == 200
    assert undone.json()["position"] == {"series": "primary", "last": "navasana"}
    assert api.delete(f"{URL}/events/{first}", headers=_auth()).json()["set"] is False


def test_practice_put_hints_and_not_new_silences_it(api: TestClient) -> None:
    _set(api, "primary", "navasana")
    day = _today()
    api.put(f"/api/v1/me/days/{day}", json={"status": "practiced"}, headers=_auth())
    body = {"context": "mysore", "length": {"series": ["primary"], "end": "kurmasana"}}
    url = f"/api/v1/me/days/{day}/practices/1"

    first = api.put(url, json=body, headers=_auth()).json()
    again = api.put(url, json=body, headers=_auth()).json()  # the length didn't change

    assert first["new_asana_hint"] == {"series": "primary", "last": "kurmasana"}
    assert again["new_asana_hint"] is None
    dismissed = api.post(
        f"{URL}/hint-dismissals",
        json={"series": "primary", "last": "kurmasana"},
        headers=_auth(),
    )
    assert dismissed.status_code == 204
    api.put(url, json=body | {"length": {"series": ["primary"]}}, headers=_auth())
    back = api.put(url, json=body, headers=_auth()).json()
    assert back["new_asana_hint"] is None


def test_presets_include_mine(api: TestClient) -> None:
    _set(api, "intermediate", "pincha-mayurasana")
    day = _today()
    found = api.get(f"/api/v1/me/days/{day}/practice-presets", headers=_auth()).json()
    mine = [p["length"] for p in found["presets"] if p["kind"] == "mine"]
    assert mine == [
        {"series": ["primary", "intermediate"], "end": "pincha-mayurasana", "first_part": None},
        {"series": ["intermediate"], "end": "pincha-mayurasana", "first_part": None},
    ]


def test_catalog_lists_milestone_items_and_shown_traditional_names(api: TestClient) -> None:
    catalog = api.get("/api/v1/catalog").json()
    traditional = {s["slug"]: s["traditional"] for s in catalog["series"]}
    assert traditional["primary"]["latin"] == "Yoga Chikitsa"
    assert traditional["intermediate"]["ru"] == "Нади Шодхана"
    assert traditional["advanced-a"] is None  # Sthira Bhaga names all of Advanced A-D
    items = catalog["milestone_items"]
    assert [i["key"] for i in items] == ["drop-backs", "standing-up", "viparita-chakrasana"]
    assert items[0]["ru"] == "Дроп-бэки"


def test_openapi_lists_the_error_codes(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()
    codes = schema["components"]["schemas"]["ErrorCode"]["enum"]
    assert {"invalid_progression", "progression_changed", "not_latest"} <= set(codes)
    assert "/api/v1/me/progression/events/{event_id}" in schema["paths"]
