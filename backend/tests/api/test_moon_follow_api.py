"""MD-02 over the API (spec §4, §7): `Location` gains the source, "Follow my teacher" and the
teacher it names; `{slug: null}` stores "Follow my teacher"; the sentinel is no slug; the
teacher's raw `moon_location` never leaves the server; Days follow the effective city."""

import json
import time as clock
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FakeNotifier, InMemoryStorage
from tests.moon_follow_fakes import following_storage, person
from tristhana.api.initdata import sign
from tristhana.domain.accounts import Account
from tristhana.domain.moon import FOLLOW_TEACHER, MoonDay, MoonDayKind
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
KEYS = {"slug", "explicit", "source", "follow_chosen", "teacher", "shared", "shala"}


def _auth(user_id: int = 42) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(clock.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    s = following_storage()
    today = datetime.now(UTC).date()
    s.moon_repo.days_by_location["mysuru"] = [
        MoonDay(today + timedelta(days=5), MoonDayKind.PURNIMA)
    ]
    s.moon_repo.days_by_location["almaty"] = [
        MoonDay(today + timedelta(days=4), MoonDayKind.PURNIMA)
    ]
    return s


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage, FakeNotifier())) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage, moon: str | None = None) -> Account:
    assert api.get("/api/v1/me", headers=_auth()).status_code == 200
    [me] = [a for a in storage.repo.accounts.values() if a.display_name == "Аня"]
    if moon is not None:
        storage.repo.accounts[me.id] = replace(storage.repo.accounts[me.id], moon_location=moon)
    return me


def _teacher(
    storage: InMemoryStorage, me: Account, moon: str | None, name: str = "Anna"
) -> Account:
    teacher = person(storage, "1001", name, moon=moon)
    storage.teacher_links.add(me.id, teacher.id)
    return teacher


def _location(api: TestClient) -> dict[str, Any]:
    response = api.get("/api/v1/me/moon-days", headers=_auth())
    assert response.status_code == 200
    return response.json()["location"]


def test_the_location_has_exactly_the_new_keys(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)

    assert set(_location(api)) == KEYS


def test_never_chose_without_a_teacher_is_the_default(
    api: TestClient, storage: InMemoryStorage
) -> None:
    _me(api, storage)

    assert _location(api) == {
        "slug": "mysuru",
        "explicit": False,
        "source": "default",
        "follow_chosen": False,
        "teacher": None,
        "shared": None,
        "shala": None,
    }


def test_never_chose_follows_the_main_teachers_city(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    anna = _teacher(storage, me, "almaty")

    body = api.get("/api/v1/me/moon-days", headers=_auth()).json()

    assert body["location"] == {
        "slug": "almaty",
        "explicit": False,
        "source": "teacher",
        "follow_chosen": False,
        "teacher": {"id": str(anna.id), "name": "Anna"},
        "shared": None,
        "shala": None,
    }
    assert [d["date"] for d in body["days"]] == [
        (datetime.now(UTC).date() + timedelta(days=4)).isoformat()
    ]


def test_a_chosen_city_names_no_teacher(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage, "moscow")
    _teacher(storage, me, "almaty")

    location = _location(api)

    assert (location["slug"], location["source"], location["teacher"]) == ("moscow", "chosen", None)
    assert location["explicit"] is True


def test_following_a_teacher_without_a_city_names_them_for_the_none_line(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage, FOLLOW_TEACHER)
    anna = _teacher(storage, me, None)

    location = _location(api)

    assert location == {
        "slug": "mysuru",
        "explicit": True,
        "source": "default",
        "follow_chosen": True,
        "teacher": {"id": str(anna.id), "name": "Anna"},
        "shared": None,
        "shala": None,
    }


def test_a_teacher_whose_teacher_has_no_city_is_named_nowhere(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """Decision 2: a never-chose student of a teacher without a city sees the plain default."""
    me = _me(api, storage)
    _teacher(storage, me, FOLLOW_TEACHER)

    location = _location(api)

    assert (location["slug"], location["source"], location["teacher"]) == (
        "mysuru",
        "default",
        None,
    )


@pytest.mark.parametrize(
    ("moon", "shared"), [("almaty", {"chosen": True}), (None, {"chosen": False})]
)
def test_shared_is_only_for_someone_with_students(
    api: TestClient, storage: InMemoryStorage, moon: str | None, shared: dict[str, bool]
) -> None:
    me = _me(api, storage, moon)
    assert _location(api)["shared"] is None
    student = person(storage, "2001", "Student")
    storage.teacher_links.add(student.id, me.id)

    assert _location(api)["shared"] == shared


def test_put_null_stores_follow_my_teacher(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage, "moscow")
    anna = _teacher(storage, me, "almaty")

    response = api.put("/api/v1/me/moon-location", json={"slug": None}, headers=_auth())

    assert response.status_code == 200
    assert response.json() == {
        "slug": "almaty",
        "explicit": True,
        "source": "teacher",
        "follow_chosen": True,
        "teacher": {"id": str(anna.id), "name": "Anna"},
        "shared": None,
        "shala": None,
    }
    assert storage.repo.accounts[me.id].moon_location == FOLLOW_TEACHER


def test_put_null_works_without_a_teacher(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage, "moscow")

    response = api.put("/api/v1/me/moon-location", json={"slug": None}, headers=_auth())

    assert response.json()["source"] == "default"
    assert response.json()["follow_chosen"] is True
    assert storage.repo.accounts[me.id].moon_location == FOLLOW_TEACHER


def test_put_a_city_answers_with_the_new_location(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    _teacher(storage, me, "almaty")

    response = api.put("/api/v1/me/moon-location", json={"slug": "moscow"}, headers=_auth())

    assert set(response.json()) == KEYS
    assert (response.json()["slug"], response.json()["source"]) == ("moscow", "chosen")


def test_the_sentinel_is_not_a_slug(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage, "moscow")

    response = api.put("/api/v1/me/moon-location", json={"slug": FOLLOW_TEACHER}, headers=_auth())

    assert (response.status_code, response.json()) == (422, {"code": "unknown_location"})
    assert storage.repo.accounts[me.id].moon_location == "moscow"


def test_days_follow_the_effective_city(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    _teacher(storage, me, "almaty")

    body = api.get("/api/v1/me/days", headers=_auth()).json()

    assert body["moon_location"] == "almaty"


def test_the_openapi_never_carries_a_teachers_raw_moon_location(api: TestClient) -> None:
    schemas = api.get("/openapi.json").json()["components"]["schemas"]
    location = schemas["Location"]["properties"]

    assert set(location) == KEYS
    assert location["source"].get("enum") or "$ref" in str(location["source"])
    teacher = json.dumps(location["teacher"])
    ref = next(
        (name for name in schemas if f'"#/components/schemas/{name}"' in teacher),
        None,
    )
    assert ref is not None, "teacher is a named schema"
    assert set(schemas[ref]["properties"]) == {"id", "name"}
    for name in ("TeacherOut", "StudentOut", "LinksOut"):
        assert "moon_location" not in json.dumps(schemas[name])
