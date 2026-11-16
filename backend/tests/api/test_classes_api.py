"""Class and schedule endpoints (SC-02 spec §4, §7): auth; the exact shapes; 404 for
non-members, the same as an unknown id; 403 `not_allowed` for an assistant's or a student's
write; 1:1 rows absent for students (Q121); `from` bounds from the shala's today and `days`
1..31 as 422; `invalid_class` (422) and `class_caps` (409); `rrule` in `ClassOut`; the split
with `from`; cancel and restore; closures; swaps (Q125); the shala's day off and moon policy;
`no-store`; and the Mini App's contract. A frozen clock (Sat 7 Nov 2026, 11:00 Almaty)."""

import json
import re
import time as wall
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.api.initdata import sign
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider
from tristhana.domain.classes import MAX_CLASSES, ClassType, Override
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.shalas import ShalaRole
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
TODAY = date(2026, 11, 7)
MON, FRI, SAT = date(2026, 11, 9), date(2026, 11, 13), date(2026, 11, 14)
SCHEDULE_KEYS = {"zone", "city", "moon_policy", "days_off", "days", "occurrences", "closures"}
DAY_KEYS = {"date", "moon", "day_off", "swap_from"}
SC02_OCCURRENCE_KEYS = {
    "class_id",
    "key",
    "on",
    "start",
    "end",
    "starts_at",
    "type",
    "title",
    "online",
    "teacher",
    "substitute",
    "cancelled",
    "moved",
    "swapped_from",
    "held",
    "usual_teacher",
}
# SC-03 (spec §4): the shala schedule gains `moon` and `swapped_to`; `/me/classes` keeps the
# SC-02 shape while it is deprecated.
# SC-05 (spec §4): staff counts on every schedule row (null for a student).
OCCURRENCE_KEYS = SC02_OCCURRENCE_KEYS | {"moon", "swapped_to", "attendance_counts"}
CLASS_KEYS = {
    "id",
    "type",
    "title",
    "online",
    "city",
    "teacher_id",
    "start",
    "minutes",
    "weekdays",
    "every",
    "starts_on",
    "ends_on",
    "rrule",
}
CLASS_IN = {
    "type": "mysore",
    "title": None,
    "online": False,
    "city": None,
    "teacher_id": None,
    "start": "06:00",
    "minutes": 210,
    "weekdays": [1, 2, 3, 4, 5],
    "every": 1,
    "starts_on": "2026-11-09",
    "ends_on": None,
}


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
    return storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(ME_TG))]


def _anna(storage: InMemoryStorage) -> Account:
    return person(storage, "1001", "Anna")


def _shala(storage: InMemoryStorage, me: UUID, role: str | None, **kw: Any) -> UUID:
    """A shala owned by Anna, with me in `role` (None: a student; "owner": mine)."""
    if role == "owner":
        return storage.shalas.add_shala(me, **kw).id
    anna = _anna(storage)
    shala = storage.shalas.add_shala(anna.id, **kw).id
    if role is None:
        storage.shalas.add_student(shala, me)
    elif role != "nobody":
        storage.shalas.add_staff(shala, me, ShalaRole(role))
    return shala


def _routes(shala: UUID, cls: UUID) -> list[tuple[str, str, dict[str, Any] | None]]:
    base = f"/api/v1/shalas/{shala}"
    return [
        ("GET", f"{base}/schedule?from=2026-11-09&days=7", None),
        ("GET", f"{base}/classes", None),
        ("POST", f"{base}/classes", CLASS_IN),
        ("PATCH", f"{base}/classes/{cls}", {"minutes": 180}),
        ("DELETE", f"{base}/classes/{cls}", None),
        ("PUT", f"{base}/classes/{cls}/occurrences/2026-11-09", {"status": "cancelled"}),
        ("DELETE", f"{base}/classes/{cls}/occurrences/2026-11-09", None),
        ("POST", f"{base}/closures", {"start": "2026-12-24", "end": "2026-12-26"}),
        ("DELETE", f"{base}/closures/{uuid4()}", None),
        ("POST", f"{base}/swaps", {"from": "2026-11-13", "to": "2026-11-14"}),
        ("DELETE", f"{base}/swaps/2026-11-13", None),
    ]


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.parametrize(("method", "url", "body"), _routes(uuid4(), uuid4()))
def test_every_route_needs_auth(
    api: TestClient, method: str, url: str, body: dict[str, Any] | None
) -> None:
    response = api.request(method, url, json=body)

    assert (response.status_code, response.json()) == (401, {"code": "auth_missing"})


# The schedule


def test_a_student_reads_the_week(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None, days_off=frozenset({6}))
    anna = next(a for a in storage.repo.accounts.values() if a.display_name == "Anna")
    storage.schedule.add_class(shala, teacher_id=anna.id, title="Early")

    response = api.get(
        f"/api/v1/shalas/{shala}/schedule",
        params={"from": "2026-11-09", "days": 7},
        headers=_auth(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == SCHEDULE_KEYS
    assert body["zone"] == "Asia/Almaty"
    assert (body["moon_policy"], body["days_off"]) == ("closed", [6])
    assert [d["date"] for d in body["days"]] == [
        (MON + timedelta(days=i)).isoformat() for i in range(7)
    ]
    assert all(set(d) == DAY_KEYS for d in body["days"])
    assert [d["date"] for d in body["days"] if d["day_off"]] == ["2026-11-14"]
    first = body["occurrences"][0]
    assert set(first) == OCCURRENCE_KEYS
    assert (first["key"], first["on"], first["start"], first["end"]) == (
        "2026-11-09",
        "2026-11-09",
        "06:00",
        "09:30",
    )
    assert _instant(first["starts_at"]) == datetime(2026, 11, 9, 1, 0, tzinfo=UTC)
    assert (first["type"], first["title"], first["online"]) == ("mysore", "Early", False)
    assert first["teacher"] == {"id": str(anna.id), "name": "Anna"}
    assert (first["substitute"], first["cancelled"], first["moved"], first["swapped_from"]) == (
        False,
        None,
        False,
        None,
    )
    assert len(body["occurrences"]) == 5


def test_a_moon_day_is_cancelled_and_marked(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None)
    storage.moon_repo.days_by_location["almaty"] = [MoonDay(FRI, MoonDayKind.PURNIMA)]
    storage.schedule.add_class(shala)

    body = api.get(
        f"/api/v1/shalas/{shala}/schedule",
        params={"from": "2026-11-13", "days": 1},
        headers=_auth(),
    ).json()

    assert [d["moon"] for d in body["days"]] == [True]
    assert [o["cancelled"] for o in body["occurrences"]] == ["moon"]


def test_one_to_one_rows_are_absent_for_students(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None)
    storage.schedule.add_class(shala, type=ClassType.PRIVATE, start=time(12, 0), minutes=60)
    storage.schedule.add_class(shala)
    url = f"/api/v1/shalas/{shala}/schedule"

    as_student = api.get(url, params={"from": "2026-11-09", "days": 1}, headers=_auth()).json()
    storage.shalas.add_staff(shala, me, ShalaRole.ASSISTANT)
    as_staff = api.get(url, params={"from": "2026-11-09", "days": 1}, headers=_auth()).json()

    assert [o["type"] for o in as_student["occurrences"]] == ["mysore"]
    assert sorted(o["type"] for o in as_staff["occurrences"]) == ["mysore", "private"]


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-10-30", "days": 7},  # today - 8
        {"from": "2027-11-08", "days": 1},  # today + 366
        {"from": "2026-11-09", "days": 32},
        {"from": "2026-11-09", "days": 0},
        {"from": "9 Nov", "days": 7},
    ],
)
def test_the_window_bounds_are_422(
    api: TestClient, storage: InMemoryStorage, params: dict[str, Any]
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None)

    response = api.get(f"/api/v1/shalas/{shala}/schedule", params=params, headers=_auth())

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params", [{"from": "2026-10-31", "days": 31}, {"from": "2027-11-07", "days": 1}]
)
def test_the_window_bounds_inclusive(
    api: TestClient, storage: InMemoryStorage, params: dict[str, Any]
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None)

    response = api.get(f"/api/v1/shalas/{shala}/schedule", params=params, headers=_auth())

    assert response.status_code == 200, response.text


# Non-members and roles


def test_non_member_404_equals_unknown_id_404(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "nobody")
    cls = storage.schedule.add_class(shala).id

    for method, url, body in _routes(shala, cls):
        real = api.request(method, url, json=body, headers=_auth())
        unknown = api.request(
            method, url.replace(str(shala), str(uuid4())), json=body, headers=_auth()
        )
        assert (real.status_code, real.json()) == (404, {"code": "not_found"}), url
        assert (unknown.status_code, unknown.content) == (real.status_code, real.content), url
    assert storage.schedule.writes == []


@pytest.mark.parametrize("role", [None, "assistant"])
def test_an_assistant_or_student_write_is_403(
    api: TestClient, storage: InMemoryStorage, role: str | None
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, role)
    cls = storage.schedule.add_class(shala).id

    for method, url, body in _routes(shala, cls)[1:]:  # all but the schedule read
        response = api.request(method, url, json=body, headers=_auth())
        assert (response.status_code, response.json()) == (403, {"code": "not_allowed"}), url
    assert storage.schedule.writes == []


@pytest.mark.parametrize("role", ["owner", "admin", "teacher", "office"])
def test_who_may_create_a_class(api: TestClient, storage: InMemoryStorage, role: str) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, role)

    response = api.post(f"/api/v1/shalas/{shala}/classes", json=CLASS_IN, headers=_auth())

    assert response.status_code == 201, response.text


# Classes


def test_create_returns_class_out_with_its_rrule(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")

    response = api.post(
        f"/api/v1/shalas/{shala}/classes",
        json=CLASS_IN | {"every": 2, "ends_on": "2026-12-31"},
        headers=_auth(),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == CLASS_KEYS
    assert (body["start"], body["minutes"], body["weekdays"]) == ("06:00", 210, [1, 2, 3, 4, 5])
    assert re.fullmatch(
        r"FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TU,WE,TH,FR;UNTIL=20261231(T\d{6}Z)?", body["rrule"]
    )
    listed = api.get(f"/api/v1/shalas/{shala}/classes", headers=_auth()).json()
    assert [c["id"] for c in listed] == [body["id"]]


def test_a_one_off_has_no_rrule(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")

    body = api.post(
        f"/api/v1/shalas/{shala}/classes",
        json=CLASS_IN | {"type": "conference", "weekdays": [], "starts_on": "2026-11-15"},
        headers=_auth(),
    ).json()

    assert body["rrule"] is None


@pytest.mark.parametrize(
    "bad",
    [
        {"minutes": 481},
        {"start": "22:00", "minutes": 121},
        {"every": 5},
        {"weekdays": [8]},
        {"ends_on": "2026-11-08"},
        {"title": "x" * 49},
    ],
)
def test_an_invalid_class_is_422(
    api: TestClient, storage: InMemoryStorage, bad: dict[str, Any]
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")

    response = api.post(f"/api/v1/shalas/{shala}/classes", json=CLASS_IN | bad, headers=_auth())

    assert response.status_code == 422  # the schema or the domain refuses it
    assert storage.schedule.writes == []


def test_a_class_past_midnight_is_invalid_class(api: TestClient, storage: InMemoryStorage) -> None:
    """A cross-field rule only the domain knows: the `{code}` body."""
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")

    response = api.post(
        f"/api/v1/shalas/{shala}/classes",
        json=CLASS_IN | {"start": "22:00", "minutes": 121},
        headers=_auth(),
    )

    assert (response.status_code, response.json()) == (422, {"code": "invalid_class"})


def test_the_class_cap_is_409(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    for _ in range(MAX_CLASSES):
        storage.schedule.add_class(shala)

    response = api.post(f"/api/v1/shalas/{shala}/classes", json=CLASS_IN, headers=_auth())

    assert (response.status_code, response.json()) == (409, {"code": "class_caps"})


def test_patch_from_a_date_returns_the_new_series(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    old = storage.schedule.add_class(shala)

    response = api.patch(
        f"/api/v1/shalas/{shala}/classes/{old.id}",
        json={"start": "07:00", "from": "2026-11-16"},
        headers=_auth(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] != str(old.id)
    assert (body["start"], body["starts_on"]) == ("07:00", "2026-11-16")


# UI-06 stage 4 (spec §3, §6; ADR-0048): class editing through the existing `PATCH`


def _patch(api: TestClient, shala: UUID, cls: UUID, body: dict[str, Any]) -> Any:
    return api.patch(f"/api/v1/shalas/{shala}/classes/{cls}", json=body, headers=_auth())


def test_patch_changes_only_what_was_sent(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "office")
    anna = storage.shalas.shalas[shala].owner_id
    old = storage.schedule.add_class(
        shala,
        type=ClassType.LED,
        title="Led Primary",
        teacher_id=anna,
        start=time(7, 30),
        minutes=90,
        weekdays=frozenset({5}),
        every=2,
        starts_on=date(2026, 11, 13),
        ends_on=date(2027, 3, 26),
    )
    before = api.get(f"/api/v1/shalas/{shala}/classes", headers=_auth()).json()[0]

    response = _patch(api, shala, old.id, {"minutes": 105})

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == CLASS_KEYS
    assert response.json() == before | {"minutes": 105}
    assert storage.schedule.reads[-2:] == ["classes_of", "update"]  # 3 statements with me


def test_patch_null_clears_what_may_be_empty(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    old = storage.schedule.add_class(
        shala, title="Early", online=True, city="berlin", teacher_id=me, ends_on=date(2027, 1, 31)
    )

    response = _patch(
        api, shala, old.id, {"title": None, "city": None, "teacher_id": None, "ends_on": None}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["title"], body["city"], body["teacher_id"], body["ends_on"]) == (None,) * 4
    assert (body["id"], body["online"], body["start"]) == (str(old.id), True, "06:00")


@pytest.mark.parametrize(
    "field", ["type", "online", "start", "minutes", "weekdays", "every", "starts_on"]
)
def test_patch_null_for_a_field_that_cannot_be_empty_is_422(
    api: TestClient, storage: InMemoryStorage, field: str
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    old = storage.schedule.add_class(shala)

    response = _patch(api, shala, old.id, {field: None})

    assert (response.status_code, response.json()) == (422, {"code": "invalid_class"})
    assert storage.schedule.of(shala) == [old]


def test_an_empty_patch_changes_nothing(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    old = storage.schedule.add_class(shala, title="Early")

    response = _patch(api, shala, old.id, {})

    assert response.status_code == 200, response.text
    assert storage.schedule.of(shala) == [old]


def test_patch_an_unknown_or_foreign_class_is_404(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    storage.schedule.add_class(shala)
    boris = person(storage, "1003", "Boris")
    theirs = storage.schedule.add_class(storage.shalas.add_shala(boris.id).id)

    for cls in (uuid4(), theirs.id):
        response = _patch(api, shala, cls, {"minutes": 180, "from": "2026-11-09"})
        assert (response.status_code, response.json()) == (404, {"code": "not_found"})
    assert storage.schedule.writes == []


@pytest.mark.parametrize("body", [{"minutes": 180}, {"minutes": 180, "ends_on": "2027-01-31"}])
def test_patch_from_a_date_on_a_class_that_ended_before_it_is_404(
    api: TestClient, storage: InMemoryStorage, body: dict[str, Any]
) -> None:
    """D3: someone else split it a moment ago. The form closes with "this class has changed"
    (404), and no second successor appears, whether a last date was sent or not."""
    me = _me(api, storage)
    shala = _shala(storage, me, "teacher")
    ended = storage.schedule.add_class(shala, ends_on=date(2026, 11, 8))
    storage.schedule.add_class(shala, starts_on=MON, start=time(7, 0))  # the successor
    before = storage.schedule.of(shala)

    response = _patch(api, shala, ended.id, body | {"from": "2026-11-09"})

    assert (response.status_code, response.json()) == (404, {"code": "not_found"})
    assert storage.schedule.of(shala) == before
    assert storage.schedule.writes == []


def test_patch_from_a_date_keeps_an_every_two_weeks_rhythm(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """D2: Mondays every 2 weeks from 2 Nov (2, 16, 30). Asked from Mon 9 Nov, an off week:
    the new series starts on 16 Nov, so the class does not jump to the other weeks."""
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    old = storage.schedule.add_class(
        shala, weekdays=frozenset({1}), every=2, starts_on=date(2026, 11, 2)
    )

    response = _patch(api, shala, old.id, {"start": "07:00", "from": "2026-11-09"})

    assert response.status_code == 200, response.text
    assert (response.json()["starts_on"], response.json()["every"]) == ("2026-11-16", 2)
    schedule = api.get(
        f"/api/v1/shalas/{shala}/schedule",
        params={"from": "2026-11-02", "days": 31},
        headers=_auth(),
    ).json()
    assert [(o["on"], o["start"]) for o in schedule["occurrences"]] == [
        ("2026-11-02", "06:00"),
        ("2026-11-16", "07:00"),
        ("2026-11-30", "07:00"),
    ]


def test_patch_from_today_leaves_the_past_and_carries_todays_marks(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """D1: today's class is edited after it ran (Sat 7 Nov, 11:00 Almaty; it began at 06:00).
    Earlier dates keep the old id and the old title; today's marks follow the new id, so the
    roster still shows them and a second claim meets the row instead of adding one."""
    me = _me(api, storage)
    storage.repo.accounts[me] = replace(storage.repo.accounts[me], timezone="Asia/Almaty")
    shala = _shala(storage, me, "teacher")
    vera = person(storage, "1002", "Vera")
    storage.shalas.add_student(shala, vera.id)
    old = storage.schedule.add_class(
        shala, weekdays=frozenset(range(1, 8)), starts_on=date(2026, 10, 1)
    )
    storage.attendance  # attaches the fake to the schedule  # noqa: B018
    base = f"/api/v1/shalas/{shala}/classes"

    def roster(cls: object, key: str) -> str:
        return f"{base}/{cls}/occurrences/{key}/attendance"

    for key in ("2026-11-06", "2026-11-07"):
        marked = api.patch(roster(old.id, key), json={"present": [str(vera.id)]}, headers=_auth())
        assert marked.status_code == 200, marked.text
    mine = api.put(f"/api/v1/me/attendance/{old.id}/2026-11-07", headers=_auth())
    assert (mine.status_code, mine.json()["state"]) == (200, "confirmed")  # a staff seat

    patched = _patch(api, shala, old.id, {"title": "Morning Mysore", "from": "2026-11-07"})

    assert patched.status_code == 200, patched.text
    new = patched.json()["id"]
    assert (new != str(old.id), patched.json()["starts_on"]) == (True, "2026-11-07")
    schedule = api.get(
        f"/api/v1/shalas/{shala}/schedule", params={"from": "2026-11-05", "days": 4},
        headers=_auth(),
    ).json()  # fmt: skip
    rows = {o["key"]: o for o in schedule["occurrences"]}
    assert [(k, r["class_id"] == new, r["title"]) for k, r in rows.items()] == [
        ("2026-11-05", False, None),
        ("2026-11-06", False, None),
        ("2026-11-07", True, "Morning Mysore"),
        ("2026-11-08", True, "Morning Mysore"),
    ]
    assert rows["2026-11-06"]["attendance_counts"] == {"confirmed": 1, "claimed": 0}
    assert rows["2026-11-07"]["attendance_counts"] == {"confirmed": 2, "claimed": 0}
    today = api.get(roster(new, "2026-11-07"), headers=_auth()).json()
    assert (today["confirmed"], today["claimed"]) == (2, 0)
    assert {p["name"]: p["state"] for p in today["people"]} == {
        "Ash": "confirmed",
        "Vera": "confirmed",
    }
    yesterday = api.get(roster(old.id, "2026-11-06"), headers=_auth()).json()
    assert (yesterday["confirmed"], yesterday["claimed"]) == (1, 0)
    # A second claim and a second mark land on the carried rows.
    again = api.put(f"/api/v1/me/attendance/{new}/2026-11-07", headers=_auth())
    assert (again.status_code, again.json()["state"]) == (200, "confirmed")
    marked = api.patch(roster(new, "2026-11-07"), json={"present": [str(vera.id)]}, headers=_auth())
    assert marked.json() == {"confirmed": 2, "claimed": 0}
    assert len(storage.attendance.rows) == 3
    # The old id no longer has that date.
    stale = api.put(f"/api/v1/me/attendance/{old.id}/2026-11-07", headers=_auth())
    assert stale.status_code in (404, 409), stale.text
    assert len(storage.attendance.rows) == 3


def test_a_split_leaves_marks_on_dates_the_new_rule_drops(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """The class stops running on Saturdays from today (Sat 7 Nov): today's mark stays on
    the ended series, with its own snapshot, and is not attached to another date."""
    me = _me(api, storage)
    storage.repo.accounts[me] = replace(storage.repo.accounts[me], timezone="Asia/Almaty")
    shala = _shala(storage, me, "teacher")
    old = storage.schedule.add_class(
        shala, weekdays=frozenset(range(1, 8)), starts_on=date(2026, 10, 1)
    )
    storage.attendance  # noqa: B018
    assert api.put(f"/api/v1/me/attendance/{old.id}/2026-11-07", headers=_auth()).status_code == 200

    patched = _patch(api, shala, old.id, {"weekdays": [1, 2, 3, 4, 5], "from": "2026-11-07"})

    assert patched.status_code == 200, patched.text
    assert list(storage.attendance.rows) == [(old.id, TODAY, me)]


def test_delete_is_204_and_idempotent(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    cls = storage.schedule.add_class(shala).id

    for _ in range(2):
        response = api.delete(f"/api/v1/shalas/{shala}/classes/{cls}", headers=_auth())
        assert response.status_code == 204


# Occurrences


def test_cancel_then_restore(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "teacher")
    cls = storage.schedule.add_class(shala).id
    url = f"/api/v1/shalas/{shala}/classes/{cls}/occurrences/2026-11-09"

    cancelled = api.put(url, json={"status": "cancelled"}, headers=_auth())
    restored = api.delete(url, headers=_auth())

    assert cancelled.status_code == 200, cancelled.text
    assert set(cancelled.json()) == OCCURRENCE_KEYS
    assert cancelled.json()["cancelled"] == "cancelled"
    assert restored.status_code == 204
    assert (cls, MON) not in storage.schedule.overrides


def test_hold_anyway_on_a_moon_day(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "office")
    storage.moon_repo.days_by_location["almaty"] = [MoonDay(FRI, MoonDayKind.AMAVASYA)]
    cls = storage.schedule.add_class(shala).id

    response = api.put(
        f"/api/v1/shalas/{shala}/classes/{cls}/occurrences/2026-11-13",
        json={"status": "held"},
        headers=_auth(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["cancelled"] is None


def test_a_move_of_seven_days_is_422(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    cls = storage.schedule.add_class(shala).id

    response = api.put(
        f"/api/v1/shalas/{shala}/classes/{cls}/occurrences/2026-11-09",
        json={"on": "2026-11-16"},
        headers=_auth(),
    )

    assert (response.status_code, response.json()) == (422, {"code": "invalid_class"})


def test_a_substitute_shows_on_the_schedule(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    cls = storage.schedule.add_class(shala, teacher_id=me).id
    dana = person(storage, "1003", "Dana")
    storage.shalas.add_staff(shala, dana.id, ShalaRole.TEACHER)
    storage.schedule.add_override(
        cls,
        Override(
            on_date=MON,
            status=None,
            moved_to=None,
            start=None,
            minutes=None,
            teacher_id=dana.id,
        ),
    )

    body = api.get(
        f"/api/v1/shalas/{shala}/schedule",
        params={"from": "2026-11-09", "days": 1},
        headers=_auth(),
    ).json()

    [o] = body["occurrences"]
    assert (o["teacher"], o["substitute"]) == ({"id": str(dana.id), "name": "Dana"}, True)


# My classes


def test_my_classes_name_whose_and_who_covers(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "teacher", name="Ashtanga Almaty")
    anna = storage.shalas.shalas[shala].owner_id  # on the staff as a teacher
    mine = storage.schedule.add_class(shala, teacher_id=me).id
    storage.schedule.add_class(shala, type=ClassType.LED, teacher_id=anna, weekdays={2})
    covered = Override(MON, None, teacher_id=anna)
    storage.schedule.add_override(mine, covered)
    led = next(c for _, c in storage.schedule.classes.values() if c.type is ClassType.LED)
    storage.schedule.add_override(led.id, Override(date(2026, 11, 10), None, teacher_id=me))

    response = api.get("/api/v1/me/classes", headers=_auth())

    assert response.status_code == 200
    [one] = response.json()
    assert set(one) == {"shala_id", "name", "zone", "today", "classes"}
    assert (one["name"], one["zone"], one["today"]) == (
        "Ashtanga Almaty",
        "Asia/Almaty",
        "2026-11-07",
    )
    rows = {(c["on"], c["type"]): c for c in one["classes"]}
    assert set(next(iter(rows.values()))) == SC02_OCCURRENCE_KEYS | {"role"}
    monday = rows[("2026-11-09", "mysore")]
    assert (monday["role"], monday["teacher"]["name"]) == ("covered", "Anna")
    tuesday = rows[("2026-11-10", "led")]
    assert (tuesday["role"], tuesday["usual_teacher"]["name"]) == ("covering", "Anna")
    assert rows[("2026-11-10", "mysore")]["role"] == "teaching"


def test_my_classes_need_auth_and_are_no_store(api: TestClient, storage: InMemoryStorage) -> None:
    assert api.get("/api/v1/me/classes").status_code == 401
    _me(api, storage)

    assert api.get("/api/v1/me/classes", headers=_auth()).headers["cache-control"] == "no-store"


def test_my_classes_for_a_student_are_empty(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None)
    storage.schedule.add_class(shala)

    assert api.get("/api/v1/me/classes", headers=_auth()).json() == []


# Closures and swaps


def test_closures_add_and_remove(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")

    created = api.post(
        f"/api/v1/shalas/{shala}/closures",
        json={"start": "2026-12-24", "end": "2026-12-26"},
        headers=_auth(),
    )
    assert created.status_code == 201, created.text
    assert set(created.json()) == {"id", "start", "end"}
    removed = api.delete(f"/api/v1/shalas/{shala}/closures/{created.json()['id']}", headers=_auth())

    assert removed.status_code == 204
    assert storage.schedule.closures == {}


def test_a_swap_to_the_day_off(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner", days_off=frozenset({6}))
    storage.moon_repo.days_by_location["almaty"] = [MoonDay(FRI, MoonDayKind.PURNIMA)]
    storage.schedule.add_class(shala)

    response = api.post(
        f"/api/v1/shalas/{shala}/swaps",
        json={"from": "2026-11-13", "to": "2026-11-14"},
        headers=_auth(),
    )
    body = api.get(
        f"/api/v1/shalas/{shala}/schedule",
        params={"from": "2026-11-13", "days": 2},
        headers=_auth(),
    ).json()

    assert response.status_code == 201, response.text
    [o] = body["occurrences"]
    assert (o["key"], o["on"], o["swapped_from"], o["cancelled"]) == (
        "2026-11-13",
        "2026-11-14",
        "2026-11-13",
        None,
    )
    assert [d["swap_from"] for d in body["days"]] == [None, "2026-11-13"]


@pytest.mark.parametrize(
    ("to", "moon"),
    [("2026-11-12", ()), ("2026-11-14", (SAT,)), ("2026-11-20", ()), ("2026-11-13", ())],
    ids=["same-type-day", "moon-day", "seven-days", "same-day"],
)
def test_an_invalid_swap_is_422(
    api: TestClient, storage: InMemoryStorage, to: str, moon: tuple[date, ...]
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner", days_off=frozenset({6}))
    storage.moon_repo.days_by_location["almaty"] = [
        MoonDay(d, MoonDayKind.PURNIMA) for d in (FRI, *moon)
    ]
    storage.schedule.add_class(shala)

    response = api.post(
        f"/api/v1/shalas/{shala}/swaps", json={"from": "2026-11-13", "to": to}, headers=_auth()
    )

    assert (response.status_code, response.json()) == (422, {"code": "invalid_class"})


# The shala's settings


def test_the_card_carries_the_day_off_moon_policy_and_schedule_right(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")

    patched = api.patch(
        f"/api/v1/shalas/{shala}",
        json={"days_off": [6], "moon_policy": "pranayama"},
        headers=_auth(),
    )

    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert (body["days_off"], body["moon_policy"]) == ([6], "pranayama")
    assert body["me"]["schedule"] is True


@pytest.mark.parametrize(
    ("role", "schedule"), [(None, False), ("assistant", False), ("teacher", True)]
)
def test_me_schedule_is_can_manage_schedule(
    api: TestClient, storage: InMemoryStorage, role: str | None, schedule: bool
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, role)

    body = api.get(f"/api/v1/shalas/{shala}", headers=_auth()).json()

    assert body["me"]["schedule"] is schedule
    assert (body["days_off"], body["moon_policy"]) == (None, "closed")


@pytest.mark.parametrize("body", [{"days_off": [5, 6, 7]}, {"moon_policy": "led"}])
def test_bad_shala_settings_are_422(
    api: TestClient, storage: InMemoryStorage, body: dict[str, Any]
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")

    response = api.patch(f"/api/v1/shalas/{shala}", json=body, headers=_auth())

    assert response.status_code == 422


def test_a_teacher_may_not_change_the_moon_policy(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "teacher")

    response = api.patch(f"/api/v1/shalas/{shala}", json={"moon_policy": "open"}, headers=_auth())

    assert (response.status_code, response.json()) == (403, {"code": "not_allowed"})


# Headers and the contract


def test_every_answer_is_no_store(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "owner")
    cls = storage.schedule.add_class(shala).id

    answers = [api.request(m, u, json=b, headers=_auth()) for m, u, b in _routes(shala, cls)]

    for answer in answers:
        assert answer.headers["cache-control"] == "no-store", answer.request.url


def test_openapi_lists_the_new_error_codes(api: TestClient) -> None:
    codes = api.get("/openapi.json").json()["components"]["schemas"]["ErrorCode"]["enum"]

    assert {"class_caps", "invalid_class"} <= set(codes)


def test_the_mini_apps_contract_has_the_routes() -> None:
    path = Path(__file__).resolve().parents[3] / "miniapp" / "src" / "api" / "openapi.json"
    paths = json.loads(path.read_text())["paths"]

    assert {
        "/api/v1/shalas/{id}/schedule",
        "/api/v1/shalas/{id}/classes",
        "/api/v1/shalas/{id}/classes/{class_id}",
        "/api/v1/shalas/{id}/classes/{class_id}/occurrences/{key}",
        "/api/v1/shalas/{id}/closures",
        "/api/v1/shalas/{id}/closures/{closure_id}",
        "/api/v1/shalas/{id}/swaps",
        "/api/v1/shalas/{id}/swaps/{from}",
        "/api/v1/me/classes",
    } <= paths.keys()
