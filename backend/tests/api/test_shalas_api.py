"""Shala endpoints (SC-01 spec §4, §7): auth, the exact shapes, 404 for non-members that reads
the same as an unknown id, 403 `not_allowed` for a member without the right, the students
list hidden from students, caps as 409 `shala_caps`, `invalid_shala_name`,
`unknown_location`, `no-store`, codes never in a path or query, `follow: "shala"`,
`source: "shala"`, and the Mini App's contract."""

import base64
import json
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
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
from tristhana.domain.shalas import MAX_OWNED, MAX_PENDING_STAFF_INVITES, ShalaRole
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
JOIN = "J0inC0deJ0inC0de"
_JOIN_URL = re.compile(rf"https://t\.me/{BOT}\?start=h_([A-Za-z0-9]{{16}})")
_STAFF_URL = re.compile(rf"https://t\.me/{BOT}\?start=hs_([A-Za-z0-9]{{16}})")
SHALA_KEYS = {
    "id",
    "name",
    "city",
    "zone",
    "online",
    "moon_city",
    "staff",
    "students_total",
    "me",
    "days_off",  # SC-02
    "moon_policy",
}
TEACHER, ASSISTANT, OFFICE, ADMIN = "teacher", "assistant", "office", "admin"
SC02_PARAMETERS = {"class_id", "key", "closure_id", "from", "days"}  # SC-02 schedule routes
SC05_PARAMETERS = {"q"}  # SC-05: the roster's name search


def _routes(shala: UUID, account: UUID) -> list[tuple[str, str, dict[str, Any] | None]]:
    return [
        ("GET", "/api/v1/me/shalas", None),
        ("POST", "/api/v1/shalas", {"name": "S", "city": "almaty", "online": False, "roles": []}),
        ("GET", f"/api/v1/shalas/{shala}", None),
        ("PATCH", f"/api/v1/shalas/{shala}", {"name": "X"}),
        ("DELETE", f"/api/v1/shalas/{shala}", None),
        ("GET", f"/api/v1/shalas/{shala}/students", None),
        ("POST", f"/api/v1/shalas/{shala}/join-link", {}),
        ("POST", f"/api/v1/shalas/{shala}/staff-invites", {"role": TEACHER}),
        ("PUT", f"/api/v1/shalas/{shala}/staff/{account}", {"roles": [TEACHER]}),
        ("DELETE", f"/api/v1/shalas/{shala}/staff/{account}", None),
        ("DELETE", f"/api/v1/shalas/{shala}/students/{account}", None),
    ]


def _auth(user_id: int = ME_TG, name: str = "Ash") -> dict[str, str]:
    profile = {"id": user_id, "first_name": name, "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return shala_storage()


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage, user_id: int = ME_TG) -> UUID:
    assert api.get("/api/v1/me", headers=_auth(user_id)).status_code == 200
    return storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(user_id))]


def _person(storage: InMemoryStorage, telegram_id: str, name: str = "Anna") -> Account:
    return person(storage, telegram_id, name)


def _shala(storage: InMemoryStorage, owner: UUID, **kw: Any) -> UUID:
    return storage.shalas.add_shala(owner, code=kw.pop("code", JOIN), **kw).id


def _owned_by_other(storage: InMemoryStorage) -> tuple[Account, UUID]:
    anna = _person(storage, "1001", "Anna")
    return anna, _shala(storage, anna.id)


@pytest.mark.parametrize(("method", "url", "body"), _routes(uuid4(), uuid4()))
def test_every_route_needs_auth(
    api: TestClient, method: str, url: str, body: dict[str, Any] | None
) -> None:
    response = api.request(method, url, json=body)

    assert (response.status_code, response.json()) == (401, {"code": "auth_missing"})


# Create and read


def test_create_returns_201_with_the_card(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)

    response = api.post(
        "/api/v1/shalas",
        json={"name": "  Ashtanga  Almaty ", "city": "almaty", "online": False, "roles": [TEACHER]},
        headers=_auth(),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == SHALA_KEYS
    assert body["name"] == "Ashtanga Almaty"
    assert body["city"] == {"slug": "almaty", "name": "Almaty"}
    assert body["zone"] == "Asia/Almaty"  # IANA; the client builds the label
    assert (body["online"], body["moon_city"]) == (False, None)
    assert body["me"] == {
        "owner": True,
        "roles": [TEACHER],
        "student": False,
        "schedule": True,
        "announce": True,  # NT-03
    }
    assert body["staff"] == [{"id": str(me), "name": "Ash", "owner": True, "roles": [TEACHER]}]
    assert body["students_total"] == 0


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"name": "   ", "city": "almaty", "online": False, "roles": []}, "invalid_shala_name"),
        ({"name": "S", "city": "atlantis", "online": False, "roles": []}, "unknown_location"),
        ({"name": "S", "city": "-shala", "online": False, "roles": []}, "unknown_location"),
    ],
)
def test_create_refusals(api: TestClient, body: dict[str, Any], code: str) -> None:
    response = api.post("/api/v1/shalas", json=body, headers=_auth())

    assert response.status_code in (400, 422)
    assert response.json() == {"code": code}


def test_create_refuses_owner_as_a_role(api: TestClient) -> None:
    response = api.post(
        "/api/v1/shalas",
        json={"name": "S", "city": "almaty", "online": False, "roles": ["owner"]},
        headers=_auth(),
    )

    assert response.status_code == 422


def test_create_at_the_cap_is_409(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    for i in range(MAX_OWNED):
        _shala(storage, me, name=f"S{i}", code=f"Code{i:012d}")

    response = api.post(
        "/api/v1/shalas",
        json={"name": "S", "city": "almaty", "online": False, "roles": []},
        headers=_auth(),
    )

    assert (response.status_code, response.json()) == (409, {"code": "shala_caps"})


def test_my_shalas_have_exactly_the_agreed_keys(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    mine = _shala(storage, me, name="Mine", city="moscow", code="Mine000000000000")
    anna, theirs = _owned_by_other(storage)
    storage.shalas.add_student(theirs, me)

    body = api.get("/api/v1/me/shalas", headers=_auth()).json()

    assert [set(row) for row in body] == [
        {"id", "name", "city", "online", "side", "owner", "roles"}
    ] * 2
    by_id = {row["id"]: row for row in body}
    assert (by_id[str(mine)]["side"], by_id[str(mine)]["owner"]) == ("staff", True)
    assert (by_id[str(theirs)]["side"], by_id[str(theirs)]["owner"]) == ("student", False)
    assert by_id[str(theirs)]["roles"] == []
    assert str(anna.id) not in json.dumps(body)


def test_a_student_sees_staff_but_no_students(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    _, shala = _owned_by_other(storage)
    storage.shalas.add_student(shala, me)
    other = _person(storage, "2001", "Bea")
    storage.shalas.add_student(shala, other.id)

    card = api.get(f"/api/v1/shalas/{shala}", headers=_auth())
    students = api.get(f"/api/v1/shalas/{shala}/students", headers=_auth())

    assert card.status_code == 200
    assert card.json()["students_total"] is None
    assert card.json()["me"] == {
        "owner": False,
        "roles": [],
        "student": True,
        "schedule": False,
        "announce": False,  # NT-03
    }
    assert [s["name"] for s in card.json()["staff"]] == ["Anna"]
    assert "Bea" not in card.text
    assert (students.status_code, students.json()) == (403, {"code": "not_allowed"})


def test_staff_page_the_students(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    _, shala = _owned_by_other(storage)
    storage.shalas.add_staff(shala, me, ShalaRole.ASSISTANT)
    for i in range(12):
        storage.shalas.add_student(shala, _person(storage, f"{3000 + i}", f"S{i:02d}").id)

    page = api.get(f"/api/v1/shalas/{shala}/students?offset=10&limit=10", headers=_auth())
    card = api.get(f"/api/v1/shalas/{shala}", headers=_auth())

    assert page.status_code == 200
    assert set(page.json()) == {"students", "total"}
    assert page.json()["total"] == 12
    assert [set(s) for s in page.json()["students"]] == [{"id", "name"}] * 2
    assert [s["name"] for s in page.json()["students"]] == ["S10", "S11"]
    assert card.json()["students_total"] == 12


def test_the_student_page_limit_is_capped(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)

    response = api.get(f"/api/v1/shalas/{shala}/students?limit=51", headers=_auth())

    assert response.status_code == 422


def test_the_online_card_and_a_moon_city(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, online=True, moon_city="mysuru")

    body = api.get(f"/api/v1/shalas/{shala}", headers=_auth()).json()

    assert (body["online"], body["moon_city"], body["zone"]) == (True, "mysuru", "Asia/Almaty")


# Non-members: 404, the same as an unknown id


def test_non_member_404_equals_unknown_id_404(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    anna, shala = _owned_by_other(storage)

    for method, url, body in _routes(shala, anna.id)[2:]:
        real = api.request(method, url, json=body, headers=_auth())
        unknown = api.request(
            method, url.replace(str(shala), str(uuid4())), json=body, headers=_auth()
        )
        assert (real.status_code, real.json()) == (404, {"code": "not_found"}), url
        assert (unknown.status_code, unknown.content) == (real.status_code, real.content), url
    assert storage.shalas.writes == []


# Members without the right: 403 not_allowed


def _member(storage: InMemoryStorage, me: UUID, role: str | None) -> UUID:
    _, shala = _owned_by_other(storage)
    if role is None:
        storage.shalas.add_student(shala, me)
    else:
        storage.shalas.add_staff(shala, me, ShalaRole(role))
    return shala


@pytest.mark.parametrize(
    ("role", "method", "path", "body", "allowed"),
    [
        (None, "PATCH", "", {"name": "X"}, False),
        (TEACHER, "PATCH", "", {"name": "X"}, False),
        (OFFICE, "PATCH", "", {"name": "X"}, False),
        (ADMIN, "PATCH", "", {"name": "X"}, True),
        (ADMIN, "DELETE", "", None, False),
        (TEACHER, "DELETE", "", None, False),
        (None, "POST", "/join-link", {}, False),
        (ASSISTANT, "POST", "/join-link", {}, True),
        (ASSISTANT, "POST", "/join-link", {"rotate": True}, False),
        (ADMIN, "POST", "/join-link", {"rotate": True}, True),
        (TEACHER, "POST", "/staff-invites", {"role": TEACHER}, False),
        (ADMIN, "POST", "/staff-invites", {"role": TEACHER}, True),
        (ADMIN, "POST", "/staff-invites", {"role": ADMIN}, False),
        (None, "POST", "/staff-invites", {"role": OFFICE}, False),
    ],
)
def test_the_role_matrix(
    api: TestClient,
    storage: InMemoryStorage,
    role: str | None,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    allowed: bool,
) -> None:
    me = _me(api, storage)
    shala = _member(storage, me, role)

    response = api.request(method, f"/api/v1/shalas/{shala}{path}", json=body, headers=_auth())

    if allowed:
        assert response.is_success, response.text
    else:
        assert (response.status_code, response.json()) == (403, {"code": "not_allowed"})


def test_owner_deletes_with_204(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)

    response = api.delete(f"/api/v1/shalas/{shala}", headers=_auth())

    assert response.status_code == 204
    assert storage.shalas.shalas == {}


def test_patch_null_moon_city_means_the_city(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me, moon_city="mysuru")

    body = api.patch(f"/api/v1/shalas/{shala}", json={"moon_city": None}, headers=_auth()).json()
    kept = api.patch(f"/api/v1/shalas/{shala}", json={"online": True}, headers=_auth()).json()

    assert body["moon_city"] is None
    assert (kept["moon_city"], kept["online"]) == (None, True)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"city": "atlantis"}, "unknown_location"),
        ({"moon_city": "-teacher"}, "unknown_location"),
        ({"name": " "}, "invalid_shala_name"),
    ],
)
def test_patch_refusals(
    api: TestClient, storage: InMemoryStorage, body: dict[str, Any], code: str
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)

    response = api.patch(f"/api/v1/shalas/{shala}", json=body, headers=_auth())

    assert response.status_code in (400, 422)
    assert response.json() == {"code": code}


# Links and invites


def test_the_join_link_is_a_deep_link_with_a_png(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)

    first = api.post(f"/api/v1/shalas/{shala}/join-link", json={}, headers=_auth())
    rotated = api.post(f"/api/v1/shalas/{shala}/join-link", json={"rotate": True}, headers=_auth())

    assert first.status_code == 200
    assert set(first.json()) == {"url", "qr"}
    match = _JOIN_URL.fullmatch(first.json()["url"])
    assert match is not None
    assert match[1] == JOIN
    prefix, png = first.json()["qr"].split(",", 1)
    assert prefix == "data:image/png;base64"
    assert base64.b64decode(png).startswith(b"\x89PNG\r\n\x1a\n")
    assert _JOIN_URL.fullmatch(rotated.json()["url"])
    assert rotated.json()["url"] != first.json()["url"]


def test_a_staff_invite_is_single_use_with_an_expiry(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)

    response = api.post(
        f"/api/v1/shalas/{shala}/staff-invites", json={"role": ASSISTANT}, headers=_auth()
    )

    assert response.status_code == 200
    assert set(response.json()) == {"url", "qr", "expires_at"}
    match = _STAFF_URL.fullmatch(response.json()["url"])
    assert match is not None
    expires = datetime.fromisoformat(response.json()["expires_at"])
    assert expires.tzinfo is not None
    assert 6.9 < (expires - datetime.now(UTC)).total_seconds() / 86400 <= 7.0
    assert storage.shalas.invites[match[1]].role is ShalaRole.ASSISTANT


def test_the_pending_invite_cap_is_409(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)
    for i in range(MAX_PENDING_STAFF_INVITES):
        storage.shalas.add_invite(shala, f"Pend{i:012d}")

    response = api.post(
        f"/api/v1/shalas/{shala}/staff-invites", json={"role": TEACHER}, headers=_auth()
    )

    assert (response.status_code, response.json()) == (409, {"code": "shala_caps"})


# Staff and students


def test_put_roles_returns_the_card(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)
    boris = _person(storage, "2002", "Boris")
    storage.shalas.add_staff(shala, boris.id, ShalaRole.TEACHER)

    response = api.put(
        f"/api/v1/shalas/{shala}/staff/{boris.id}",
        json={"roles": [TEACHER, OFFICE]},
        headers=_auth(),
    )

    assert response.status_code == 200
    assert set(response.json()) == SHALA_KEYS
    staff = {s["id"]: s for s in response.json()["staff"]}
    assert sorted(staff[str(boris.id)]["roles"]) == [OFFICE, TEACHER]


def test_put_roles_on_the_owner_is_403(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    anna, shala = _owned_by_other(storage)
    storage.shalas.add_staff(shala, me, ShalaRole.ADMIN)

    response = api.put(
        f"/api/v1/shalas/{shala}/staff/{anna.id}", json={"roles": [TEACHER]}, headers=_auth()
    )

    assert (response.status_code, response.json()) == (403, {"code": "not_allowed"})


@pytest.mark.parametrize("side", ["staff", "students"])
def test_removing_is_204_twice(api: TestClient, storage: InMemoryStorage, side: str) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)
    other = _person(storage, "2003", "Clara")
    if side == "staff":
        storage.shalas.add_staff(shala, other.id, ShalaRole.TEACHER)
    else:
        storage.shalas.add_student(shala, other.id)
    url = f"/api/v1/shalas/{shala}/{side}/{other.id}"

    first = api.delete(url, headers=_auth())
    second = api.delete(url, headers=_auth())

    assert (first.status_code, second.status_code) == (204, 204)
    assert storage.shalas.membership(shala, other.id) is None


@pytest.mark.parametrize("side", ["staff", "students"])
def test_leaving_is_removing_oneself(api: TestClient, storage: InMemoryStorage, side: str) -> None:
    me = _me(api, storage)
    _, shala = _owned_by_other(storage)
    if side == "staff":
        storage.shalas.add_staff(shala, me, ShalaRole.TEACHER)
    else:
        storage.shalas.add_student(shala, me)

    response = api.delete(f"/api/v1/shalas/{shala}/{side}/{me}", headers=_auth())

    assert response.status_code == 204
    assert storage.shalas.membership(shala, me) is None


def test_the_owner_cannot_leave(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)

    response = api.delete(f"/api/v1/shalas/{shala}/staff/{me}", headers=_auth())

    assert (response.status_code, response.json()) == (403, {"code": "not_allowed"})
    assert storage.shalas.membership(shala, me) is not None


def test_a_student_cannot_remove_another_student(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    _, shala = _owned_by_other(storage)
    storage.shalas.add_student(shala, me)
    bea = _person(storage, "2004", "Bea")
    storage.shalas.add_student(shala, bea.id)

    response = api.delete(f"/api/v1/shalas/{shala}/students/{bea.id}", headers=_auth())

    assert (response.status_code, response.json()) == (403, {"code": "not_allowed"})
    assert storage.shalas.membership(shala, bea.id) is not None


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/shalas/not-a-uuid",
        "/api/v1/shalas/{id}/staff/not-a-uuid",
        "/api/v1/shalas/{id}/students/not-a-uuid",
    ],
)
def test_a_malformed_id_is_a_validation_error(api: TestClient, url: str) -> None:
    assert api.delete(url.format(id=uuid4()), headers=_auth()).status_code == 422


# Headers and the contract


def test_every_answer_is_no_store(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shala = _shala(storage, me)

    answers = [
        api.get("/api/v1/me/shalas", headers=_auth()),
        api.get(f"/api/v1/shalas/{shala}", headers=_auth()),
        api.get(f"/api/v1/shalas/{shala}/students", headers=_auth()),
        api.post(f"/api/v1/shalas/{shala}/join-link", json={}, headers=_auth()),
        api.post(f"/api/v1/shalas/{shala}/staff-invites", json={"role": TEACHER}, headers=_auth()),
        api.patch(f"/api/v1/shalas/{shala}", json={"online": True}, headers=_auth()),
        api.get(f"/api/v1/shalas/{uuid4()}", headers=_auth()),  # errors too
    ]

    for answer in answers:
        assert answer.headers["cache-control"] == "no-store", answer.request.url


def test_no_shala_route_takes_a_code(api: TestClient) -> None:
    """Joins land in the bot (as ID-04 Q12): no accept route, no code in any URL."""
    paths: dict[str, dict[str, dict[str, Any]]] = api.get("/openapi.json").json()["paths"]

    shala_paths = [p for p in paths if "shala" in p]
    assert shala_paths
    for path in shala_paths:
        assert "code" not in path.lower(), path
        assert "accept" not in path.lower(), path
        assert "join" not in path.lower() or path.endswith("/join-link"), path
        for operation in paths[path].values():
            names = {p["name"] for p in operation.get("parameters", [])}
            assert names <= {
                "id",
                "account_id",
                "Authorization",
                "offset",
                "limit",
                *SC02_PARAMETERS,
                *SC05_PARAMETERS,
            }, (
                path,
                names,
            )


def test_openapi_lists_the_new_error_codes(api: TestClient) -> None:
    codes = api.get("/openapi.json").json()["components"]["schemas"]["ErrorCode"]["enum"]

    assert {"shala_caps", "invalid_shala_name", "not_allowed", "not_found"} <= set(codes)


def test_the_mini_apps_contract_has_the_routes() -> None:
    path = Path(__file__).resolve().parents[3] / "miniapp" / "src" / "api" / "openapi.json"
    paths = json.loads(path.read_text())["paths"]

    assert {
        "/api/v1/me/shalas",
        "/api/v1/shalas",
        "/api/v1/shalas/{id}",
        "/api/v1/shalas/{id}/students",
        "/api/v1/shalas/{id}/join-link",
        "/api/v1/shalas/{id}/staff-invites",
        "/api/v1/shalas/{id}/staff/{account_id}",
        "/api/v1/shalas/{id}/students/{account_id}",
    } <= paths.keys()


# Moon: follow my shala, source shala


def _location(api: TestClient) -> dict[str, Any]:
    response = api.get("/api/v1/me/moon-days", headers=_auth())
    assert response.status_code == 200
    return response.json()["location"]


def test_the_location_gains_the_shala_key(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)

    location = _location(api)

    assert set(location) == {
        "slug",
        "explicit",
        "source",
        "follow_chosen",
        "teacher",
        "shared",
        "shala",
    }
    assert location["shala"] is None


def test_never_chose_follows_the_shala(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    anna = _person(storage, "1001", "Anna")
    shala = _shala(storage, anna.id, name="Moscow Shala", city="moscow")
    storage.shalas.add_student(shala, me)

    location = _location(api)

    assert (location["slug"], location["source"], location["explicit"]) == (
        "moscow",
        "shala",
        False,
    )
    assert location["shala"] == {"id": str(shala), "name": "Moscow Shala"}
    assert location["teacher"] is None


def test_put_follow_shala_stores_it(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    anna = _person(storage, "1001", "Anna")
    shala = _shala(storage, anna.id, city="moscow")
    storage.shalas.add_student(shala, me)

    response = api.put(
        "/api/v1/me/moon-location", json={"slug": None, "follow": "shala"}, headers=_auth()
    )

    assert response.status_code == 200
    assert (response.json()["slug"], response.json()["source"], response.json()["explicit"]) == (
        "moscow",
        "shala",
        True,
    )
    assert storage.repo.accounts[me].moon_location == "-shala"


def test_put_null_without_follow_is_still_follow_my_teacher(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)

    api.put("/api/v1/me/moon-location", json={"slug": None}, headers=_auth())

    assert storage.repo.accounts[me].moon_location == "-teacher"


def test_an_unknown_follow_is_a_validation_error(api: TestClient) -> None:
    response = api.put(
        "/api/v1/me/moon-location", json={"slug": None, "follow": "friend"}, headers=_auth()
    )

    assert response.status_code == 422
