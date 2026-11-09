"""ST-04 `GET /api/v1/me/progression/timeline` (spec §4, §8): 401 without auth; the unset,
start-only and full payloads (celebrations per entry, a range's `first`, the series lines in
practice order, a quiet re-give, `by` / `by_name`, the start's `length`); no `undoable` on an
entry; `truncated`; the OpenAPI contract. Real use cases over the in-memory ports (with links,
so a teacher's mark reads with the name), a frozen clock."""

import asyncio
import json
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FixedClock, InMemoryStorage
from tests.teacher_link_fakes import add_person
from tests.teacher_mark_fakes import MarkingProgression, marking
from tristhana.api.initdata import sign
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.progression import (
    Change,
    EventKind,
    Position,
    Progression,
    ProgressionEvent,
)
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ME_TG = 42
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
LINKED = date(2026, 6, 1)
MINE = "/api/v1/me/progression"
URL = f"{MINE}/timeline"
PASASANA = Position("intermediate", "pasasana")
KROUNCHASANA = Position("intermediate", "krounchasana")
ENTRY_FIELDS = {
    "id",
    "kind",
    "occurred_on",
    "from",
    "to",
    "item",
    "by",
    "by_name",
    "celebrations",
    "length",
}


def _auth(user_id: int = ME_TG) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Anna", "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def repo(storage: InMemoryStorage) -> MarkingProgression:
    return marking(storage)


@pytest.fixture
def api(
    storage: InMemoryStorage, repo: MarkingProgression, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    fixed = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: fixed)
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage) -> UUID:
    assert api.get("/api/v1/me", headers=_auth()).status_code == 200
    return storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(ME_TG))]


def _timeline(api: TestClient) -> dict[str, Any]:
    found = api.get(URL, headers=_auth())
    assert found.status_code == 200, found.text
    return found.json()


def _event(api: TestClient, **body: Any) -> dict[str, Any]:
    expected = api.get(MINE, headers=_auth()).json()["last_event_id"]
    done = api.post(f"{MINE}/events", json=body | {"expected_event_id": expected}, headers=_auth())
    assert done.status_code == 201, done.text
    return done.json()


def _pos(series: str | None, last: str | None) -> dict[str, str | None]:
    return {"series": series, "last": last}


def _celebration(
    kind: str, series: str | None = None, key: str | None = None, first: Any = None
) -> dict[str, Any]:
    return {"kind": kind, "series": series, "key": key, "first": first, "count": None}


def test_the_timeline_needs_auth(api: TestClient) -> None:
    assert api.get(URL).status_code == 401


def test_unset_is_empty_and_not_set(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)

    assert _timeline(api) == {"set": False, "truncated": False, "entries": []}


def test_start_only_has_one_quiet_entry_with_its_length(
    api: TestClient, storage: InMemoryStorage
) -> None:
    _me(api, storage)
    started = _event(api, kind="set", series="primary", last="navasana")

    body = _timeline(api)

    assert (body["set"], body["truncated"]) == (True, False)
    [entry] = body["entries"]
    assert set(entry) == ENTRY_FIELDS  # no `undoable`: the timeline is read-only
    assert entry == {
        "id": started["event"]["id"],
        "kind": "start",
        "occurred_on": started["event"]["occurred_on"],
        "from": None,
        "to": _pos("primary", "navasana"),
        "item": None,
        "by": "self",
        "by_name": None,
        "celebrations": [],
        "length": {"series": ["primary"], "end": "navasana", "first_part": None},
    }


def test_a_standing_only_start_has_no_length(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    _event(api, kind="set", series=None, last=None)

    [entry] = _timeline(api)["entries"]

    assert entry["to"] == _pos(None, None)
    assert entry["length"] is None


def test_a_start_at_a_stale_key_has_no_length_and_still_reads(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    stale = Position("primary", "no-such-asana")
    start = ProgressionEvent(1, EventKind.START, date(2026, 1, 5), after=stale)
    storage.day_repo.progression_events.append((me, start))

    [entry] = _timeline(api)["entries"]

    assert (entry["to"], entry["length"], entry["celebrations"]) == (
        _pos("primary", "no-such-asana"),
        None,
        [],
    )


def test_a_full_history_reads_what_each_event_meant_newest_first(
    api: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(api, storage)
    teacher = add_person(storage.repo, "7", "Лена", "ru", "Asia/Almaty")
    storage.teacher_links.add(me, teacher.id, linked_on=LINKED)
    _event(api, kind="set", series="primary", last="navasana")
    _event(api, kind="given", series="primary", last="kurmasana")
    _event(api, kind="given", series="intermediate", last="pasasana")
    _event(api, kind="set", series="primary", last="kurmasana")  # a correction back
    _event(api, kind="given", series="intermediate", last="pasasana")  # given again
    _event(api, kind="item_given", item="drop-backs")
    current = storage.day_repo.progression_rows[me]
    state = Progression(KROUNCHASANA, current.items)
    mark = Change(EventKind.GIVEN, NOW.date(), state, PASASANA, KROUNCHASANA)
    assert asyncio.run(repo.apply(me, mark, current.last_event_id, teacher.id)) is not None

    body = _timeline(api)

    entries = body["entries"]
    assert (body["set"], body["truncated"]) == (True, False)
    assert [e["kind"] for e in entries] == [
        "given",
        "item_given",
        "given",
        "changed",
        "given",
        "given",
        "start",
    ]
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids, reverse=True)
    assert all(set(e) == ENTRY_FIELDS for e in entries)
    marked, item, again, back, across, jump, start = entries
    assert (marked["by"], marked["by_name"]) == ("teacher", "Лена")
    assert marked["celebrations"] == [_celebration("new_asana", "intermediate", "krounchasana")]
    assert (item["item"], item["by"], item["by_name"]) == ("drop-backs", "self", None)
    assert item["celebrations"] == [_celebration("item", key="drop-backs")]
    assert (again["from"], again["to"]) == (
        _pos("primary", "kurmasana"),
        _pos("intermediate", "pasasana"),
    )
    assert again["celebrations"] == []  # quiet: held before
    assert (back["from"], back["to"], back["celebrations"]) == (
        _pos("intermediate", "pasasana"),
        _pos("primary", "kurmasana"),
        [],
    )
    assert across["celebrations"] == [
        _celebration("new_asana", "intermediate", "pasasana", _pos("primary", "supta-kurmasana")),
        _celebration("series_complete", "primary"),
        _celebration("series_begins", "intermediate"),
    ]
    assert jump["celebrations"] == [
        _celebration("new_asana", "primary", "kurmasana", _pos("primary", "bhujapidasana"))
    ]
    assert (start["celebrations"], start["length"]["end"]) == ([], "navasana")
    assert [e["length"] for e in entries[:-1]] == [None] * 6  # start only


def test_after_an_unlink_the_mark_reads_a_teacher(
    api: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(api, storage)
    teacher = add_person(storage.repo, "7", "Лена", "ru", "Asia/Almaty")
    storage.teacher_links.add(me, teacher.id, linked_on=LINKED)
    _event(api, kind="set", series="intermediate", last="pasasana")
    current = storage.day_repo.progression_rows[me]
    mark = Change(EventKind.GIVEN, NOW.date(), Progression(KROUNCHASANA), PASASANA, KROUNCHASANA)
    assert asyncio.run(repo.apply(me, mark, current.last_event_id, teacher.id)) is not None
    storage.teacher_links.rows.pop((me, teacher.id))

    newest = _timeline(api)["entries"][0]

    assert (newest["by"], newest["by_name"]) == ("teacher", None)


def test_older_events_left_out_say_truncated(
    api: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tests.fakes.TIMELINE_LIMIT", 2)
    _me(api, storage)
    _event(api, kind="set", series="primary", last="navasana")
    _event(api, kind="given", series="primary", last="kurmasana")
    _event(api, kind="item_given", item="drop-backs")

    body = _timeline(api)

    assert body["truncated"] is True
    assert [e["kind"] for e in body["entries"]] == ["item_given", "given"]
    # The oldest kept event is a give; it still reads as a first time from what it holds.
    assert body["entries"][1]["celebrations"][0]["kind"] == "new_asana"


def test_only_the_callers_own_events(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    other = add_person(storage.repo, "8", "Bo", "en", "UTC")
    stranger = ProgressionEvent(99, EventKind.START, date(2026, 1, 5), after=PASASANA)
    storage.day_repo.progression_events.append((other.id, stranger))

    assert _timeline(api) == {"set": False, "truncated": False, "entries": []}


def test_the_timeline_is_in_openapi(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()
    schemas = schema["components"]["schemas"]

    get = schema["paths"][f"/api/v1{URL.removeprefix('/api/v1')}"]["get"]
    ok = get["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/TimelineOut"}
    assert set(schemas["TimelineOut"]["properties"]) == {"set", "truncated", "entries"}
    assert set(schemas["TimelineEntryOut"]["properties"]) == ENTRY_FIELDS
    assert "undoable" not in schemas["TimelineEntryOut"]["properties"]
    assert set(schemas["TimelineEntryOut"]["properties"]["by"]["enum"]) == {"self", "teacher"}
