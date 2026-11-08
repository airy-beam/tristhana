"""`GET /api/v1/me/schedule` (SC-03 spec §4, §7, §8; ADR-0035): auth; the exact key sets of
`MyScheduleOut` and its parts; `from` (my date, default my today), `days` 1..7 and `only`
validated as 422 (`invalid_range` for a `from` out of bounds); `no-store`; my moon city and
my moon days; the ⚠ shifts; rows of every shala I joined and none of a followed teacher's
other shala (Q135); `/me/classes` still answering and marked `deprecated`; the Mini App's
contract. A frozen clock: Sat 7 Nov 2026, 11:00 in Almaty."""

import json
import time as wall
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.api.initdata import sign
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider
from tristhana.domain.classes import ClassType, Override, Swap
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.shalas import ShalaRole
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # Sat 7 Nov, 11:00 Almaty
URL = "/api/v1/me/schedule"
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
OCCURRENCE_KEYS = SC02_OCCURRENCE_KEYS | {"moon", "swapped_to"}
MY_ROW_KEYS = OCCURRENCE_KEYS | {"shala_id", "zone", "city", "role", "my_teacher", "planned"}
MY_SCHEDULE_KEYS = {
    "zone",
    "zone_known",
    "today",
    "moon_city",
    "days",
    "shalas",
    "has_teachers",
    "is_staff",
    "shifts",
    "occurrences",
}
MY_DAY_KEYS = {"date", "my_moon"}
SHALA_KEYS = {"id", "name", "city", "zone", "staff"}
SHIFT_KEYS = {"zone", "city", "shala_ids", "on", "minutes"}


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


def _me(
    api: TestClient, storage: InMemoryStorage, zone: str | None = "Asia/Almaty", **kw: Any
) -> UUID:
    assert api.get("/api/v1/me", headers=_auth()).status_code == 200
    me = storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(ME_TG))]
    storage.repo.accounts[me] = replace(storage.repo.accounts[me], timezone=zone, **kw)
    return me


def _anna(storage: InMemoryStorage) -> Account:
    found = next((a for a in storage.repo.accounts.values() if a.display_name == "Anna"), None)
    return found or person(storage, "1001", "Anna")


def _shala(storage: InMemoryStorage, me: UUID, role: str | None, **kw: Any) -> UUID:
    """Anna's shala with me in `role` (None: a student; "nobody": not a member)."""
    shala = storage.shalas.add_shala(_anna(storage).id, **kw).id
    if role is None:
        storage.shalas.add_student(shala, me)
    elif role != "nobody":
        storage.shalas.add_staff(shala, me, ShalaRole(role))
    return shala


def _moon(storage: InMemoryStorage, city: str, *days: date) -> None:
    storage.moon_repo.days_by_location[city] = [MoonDay(d, MoonDayKind.PURNIMA) for d in days]


def _get(api: TestClient, **params: Any) -> Any:
    response = api.get(URL, params=params, headers=_auth())
    assert response.status_code == 200, response.text
    return response.json()


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_it_needs_auth(api: TestClient) -> None:
    response = api.get(URL)

    assert (response.status_code, response.json()) == (401, {"code": "auth_missing"})


def test_the_exact_shape(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None, name="Ashtanga Almaty")
    anna = _anna(storage)
    storage.link_repo.add(me, anna.id, primary=True)
    storage.schedule.add_class(shala, teacher_id=anna.id, title="Early")

    response = api.get(URL, headers=_auth())

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == MY_SCHEDULE_KEYS
    assert (body["zone"], body["zone_known"], body["today"]) == ("Asia/Almaty", True, "2026-11-07")
    assert body["moon_city"] == "almaty"  # never chose: follows the shala (MD-02)
    assert [d["date"] for d in body["days"]] == [f"2026-11-{d:02d}" for d in range(7, 14)]
    assert all(set(d) == MY_DAY_KEYS for d in body["days"])
    assert body["shalas"] == [
        {"id": str(shala), "name": "Ashtanga Almaty", "city": "almaty", "zone": "Asia/Almaty",
         "staff": False}
    ]  # fmt: skip
    assert (body["has_teachers"], body["is_staff"], body["shifts"]) == (True, False, [])
    first = body["occurrences"][0]
    assert set(first) == MY_ROW_KEYS
    assert (first["shala_id"], first["zone"], first["city"]) == (
        str(shala),
        "Asia/Almaty",
        "almaty",
    )
    assert (first["role"], first["my_teacher"], first["moon"], first["swapped_to"]) == (
        None,
        True,
        False,
        None,
    )
    assert (first["on"], first["start"], first["end"]) == ("2026-11-09", "06:00", "09:30")
    assert _instant(first["starts_at"]) == datetime(2026, 11, 9, 1, 0, tzinfo=UTC)
    assert first["teacher"] == {"id": str(anna.id), "name": "Anna"}
    assert len(body["occurrences"]) == 5


@pytest.mark.parametrize(
    ("params", "count"),
    [({"from": "2026-11-09", "days": 1}, 1), ({"from": "2026-11-09"}, 5), ({"days": 3}, 1)],
)
def test_from_and_days(
    api: TestClient, storage: InMemoryStorage, params: dict[str, Any], count: int
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None)
    storage.schedule.add_class(shala)

    body = _get(api, **params)

    assert len(body["days"]) == params.get("days", 7)
    assert body["days"][0]["date"] == params.get("from", "2026-11-07")
    assert len(body["occurrences"]) == count


@pytest.mark.parametrize(
    "params",
    [
        {"days": 0},
        {"days": 8},
        {"only": "everything"},
        {"only": "a"},
        {"from": "9 Nov"},
        {"from": "2026-10-30"},  # today - 8
        {"from": "2027-11-08"},  # today + 366
    ],
)
def test_bad_params_are_422(
    api: TestClient, storage: InMemoryStorage, params: dict[str, Any]
) -> None:
    _me(api, storage)

    response = api.get(URL, params=params, headers=_auth())

    assert response.status_code == 422


@pytest.mark.parametrize("start", ["2026-10-30", "2027-11-08"])
def test_a_from_out_of_bounds_is_invalid_range(
    api: TestClient, storage: InMemoryStorage, start: str
) -> None:
    _me(api, storage)

    response = api.get(URL, params={"from": start}, headers=_auth())

    assert (response.status_code, response.json()) == (422, {"code": "invalid_range"})


@pytest.mark.parametrize("start", ["2026-10-31", "2027-11-07"])
def test_the_from_bounds_are_inclusive(
    api: TestClient, storage: InMemoryStorage, start: str
) -> None:
    _me(api, storage)

    assert api.get(URL, params={"from": start, "days": 1}, headers=_auth()).status_code == 200


def test_only_filters(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "teacher")
    anna = _anna(storage)
    storage.link_repo.add(me, anna.id, primary=True)
    storage.schedule.add_class(shala, teacher_id=anna.id, weekdays=frozenset({1}))
    storage.schedule.add_class(
        shala, type=ClassType.LED, teacher_id=me, weekdays=frozenset({2}), start=time(18, 0),
        minutes=90,
    )  # fmt: skip

    found = {f: _get(api, only=f) for f in ("all", "teachers", "mine")}

    assert sorted(o["type"] for o in found["all"]["occurrences"]) == ["led", "mysore"]
    assert [o["type"] for o in found["teachers"]["occurrences"]] == ["mysore"]
    assert [(o["type"], o["role"]) for o in found["mine"]["occurrences"]] == [("led", "teaching")]
    assert all(b["is_staff"] and b["has_teachers"] for b in found.values())


def test_my_moon_day_and_the_shalas_moon_row(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage, moon_location="mysuru")
    shala = _shala(storage, me, None)
    _moon(storage, "almaty", date(2026, 11, 12))
    _moon(storage, "mysuru", date(2026, 11, 13))
    storage.schedule.add_class(shala)

    body = _get(api, **{"from": "2026-11-09"})

    assert body["moon_city"] == "mysuru"
    assert [d["date"] for d in body["days"] if d["my_moon"]] == ["2026-11-13"]
    rows = {o["on"]: o for o in body["occurrences"]}
    assert (rows["2026-11-12"]["cancelled"], rows["2026-11-12"]["moon"]) == ("moon", True)
    assert (rows["2026-11-13"]["cancelled"], rows["2026-11-13"]["moon"]) == (None, False)


def test_a_swapped_moon_class_names_its_target(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, None)
    _moon(storage, "almaty", date(2026, 11, 13))
    storage.schedule.add_class(shala)
    storage.schedule.swaps[(shala, date(2026, 11, 13))] = Swap(
        date(2026, 11, 13), date(2026, 11, 14)
    )

    body = _get(api, **{"from": "2026-11-13", "days": 2})

    assert [
        (o["on"], o["cancelled"], o["swapped_to"], o["swapped_from"]) for o in body["occurrences"]
    ] == [
        ("2026-11-13", "moon", "2026-11-14", None),
        ("2026-11-14", None, None, "2026-11-13"),
    ]


def test_the_shift_lines(api: TestClient, storage: InMemoryStorage) -> None:
    """28 Mar 2027: Berlin goes to summer time, so its 17:30 class is an hour earlier in
    Almaty from Sunday."""
    me = _me(api, storage)
    shala = _shala(storage, me, None, name="Yoga Berlin", city="berlin")
    storage.schedule.add_class(
        shala, type=ClassType.LED, start=time(17, 30), minutes=90, weekdays=frozenset({1, 7}),
        starts_on=date(2027, 3, 1),
    )  # fmt: skip

    body = _get(api, **{"from": "2027-03-22"})

    assert body["shifts"] == [
        {"zone": "Europe/Berlin", "city": "berlin", "shala_ids": [str(shala)],
         "on": "2027-03-28", "minutes": 60}
    ]  # fmt: skip
    assert all(set(s) == SHIFT_KEYS for s in body["shifts"])


def test_an_unknown_zone_falls_back_to_my_first_shala(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage, zone=None)
    _shala(storage, me, None, name="Yoga Berlin", city="berlin")

    body = _get(api)

    assert (body["zone"], body["zone_known"]) == ("Europe/Berlin", False)


def test_a_followed_teachers_other_shala_is_never_shown(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    joined = _shala(storage, me, None, name="Joined")
    hidden = _shala(storage, me, "nobody", name="Hidden Room", city="berlin")
    anna = _anna(storage)
    storage.link_repo.add(me, anna.id, primary=True)
    storage.schedule.add_class(joined, teacher_id=anna.id)
    storage.schedule.add_class(hidden, teacher_id=anna.id, title="Secret")

    response = api.get(URL, headers=_auth())

    assert "Secret" not in response.text
    assert "Hidden Room" not in response.text
    assert str(hidden) not in response.text
    assert [s["id"] for s in response.json()["shalas"]] == [str(joined)]


def test_no_shala_reads_as_an_empty_schedule(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)

    body = _get(api)

    assert (body["shalas"], body["occurrences"], body["is_staff"]) == ([], [], False)


def test_the_shala_schedule_gains_moon_and_swapped_to(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """Additive (spec §4): the SC-02 view adopts the expert's row marks."""
    me = _me(api, storage)
    shala = _shala(storage, me, None, moon_policy="open")
    _moon(storage, "almaty", date(2026, 11, 13))
    storage.schedule.add_class(shala)

    body = api.get(
        f"/api/v1/shalas/{shala}/schedule",
        params={"from": "2026-11-12", "days": 2},
        headers=_auth(),
    ).json()

    assert all(set(o) == OCCURRENCE_KEYS for o in body["occurrences"])
    assert [(o["on"], o["cancelled"], o["moon"]) for o in body["occurrences"]] == [
        ("2026-11-12", None, False),
        ("2026-11-13", None, True),  # held on the moon day under `open`
    ]


# GET /me/classes: deprecated, same answer (Q137)


def test_my_classes_still_answer_in_the_sc02_shape(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, "teacher", name="Ashtanga Almaty")
    anna = storage.shalas.shalas[shala].owner_id
    mine = storage.schedule.add_class(shala, teacher_id=me).id
    storage.schedule.add_override(mine, Override(date(2026, 11, 9), None, teacher_id=anna))

    response = api.get("/api/v1/me/classes", headers=_auth())

    assert response.status_code == 200
    [one] = response.json()
    assert set(one) == {"shala_id", "name", "zone", "today", "classes"}
    assert (one["zone"], one["today"]) == ("Asia/Almaty", "2026-11-07")
    assert all(set(c) == SC02_OCCURRENCE_KEYS | {"role"} for c in one["classes"])
    roles = {c["on"]: c["role"] for c in one["classes"]}
    assert (roles["2026-11-09"], roles["2026-11-10"]) == ("covered", "teaching")


def test_my_classes_is_deprecated_and_my_schedule_is_listed(api: TestClient) -> None:
    paths = api.get("/openapi.json").json()["paths"]

    assert paths["/api/v1/me/classes"]["get"].get("deprecated") is True
    assert "deprecated" not in paths[URL]["get"]
    names = {p["name"] for p in paths[URL]["get"]["parameters"]}
    assert {"from", "days", "only"} <= names


def test_the_mini_apps_contract_has_the_route() -> None:
    path = Path(__file__).resolve().parents[3] / "miniapp" / "src" / "api" / "openapi.json"
    paths = json.loads(path.read_text())["paths"]

    assert URL in paths
    assert paths["/api/v1/me/classes"]["get"].get("deprecated") is True


def test_my_classes_keeps_sc02s_swap_shape(api: TestClient, storage: InMemoryStorage) -> None:
    """Review fix: the deprecated route doesn't gain My schedule's kept original on day A."""
    me = _me(api, storage)
    shala = _shala(storage, me, "teacher")
    _moon(storage, "almaty", date(2026, 11, 11))
    storage.schedule.add_class(shala, teacher_id=me, weekdays=frozenset({3}))  # Wednesdays
    storage.schedule.swaps[(shala, date(2026, 11, 11))] = Swap(
        date(2026, 11, 11), date(2026, 11, 12)
    )

    [one] = api.get("/api/v1/me/classes", headers=_auth()).json()

    days = [c["on"] for c in one["classes"]]
    assert days == ["2026-11-12"]  # only B, as SC-02 returned it
