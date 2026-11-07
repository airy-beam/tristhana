"""Teacher-link endpoints (ID-04, spec §4): the exact response shape, no field that could tell a
teacher they're main, invite get-or-create and rotate, the primary's 200/404/409, idempotent
deletes keyed on the caller, `no-store`, no route taking a code, and the OpenAPI contract."""

import base64
import json
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.teacher_link_fakes import add_person
from tristhana.api.initdata import sign
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
LINKS = "/api/v1/me/links"
INVITE = "/api/v1/me/invite"
ROUTES = [
    ("GET", LINKS),
    ("POST", INVITE),
    ("PUT", f"/api/v1/me/teachers/{uuid4()}/primary"),
    ("DELETE", f"/api/v1/me/teachers/{uuid4()}"),
    ("DELETE", f"/api/v1/me/students/{uuid4()}"),
]
_URL = re.compile(rf"https://t\.me/{BOT}\?start=t_([A-Za-z0-9]{{16}})")
ME_TG = 42


def _auth(user_id: int = ME_TG) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Ash", "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


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


def _person(storage: InMemoryStorage, telegram_id: str, name: str = "Лена") -> Account:
    return add_person(storage.repo, telegram_id, name)


def _links(api: TestClient) -> dict[str, Any]:
    response = api.get(LINKS, headers=_auth())
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(("method", "url"), ROUTES)
def test_every_route_needs_auth(api: TestClient, method: str, url: str) -> None:
    response = api.request(method, url)

    assert (response.status_code, response.json()) == (401, {"code": "auth_missing"})


def test_links_of_someone_new_are_empty(api: TestClient) -> None:
    assert _links(api) == {"teachers": [], "students": []}


def test_links_have_exactly_the_agreed_keys(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    teacher, student = _person(storage, "1", "Лена"), _person(storage, "2", "Boris")
    storage.teacher_links.add(me, teacher.id)
    storage.teacher_links.add(student.id, me)

    body = _links(api)

    assert set(body) == {"teachers", "students"}
    [listed_teacher], [listed_student] = body["teachers"], body["students"]
    assert set(listed_teacher) == {"id", "name", "primary", "primary_chosen", "linked_at"}
    assert (listed_teacher["id"], listed_teacher["name"]) == (str(teacher.id), "Лена")
    assert (listed_teacher["primary"], listed_teacher["primary_chosen"]) == (True, False)
    assert set(listed_student) == {"id", "name", "linked_at"}  # no practice field, no primary
    assert (listed_student["id"], listed_student["name"]) == (str(student.id), "Boris")


def test_a_teacher_never_sees_whether_they_are_main(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    student = _person(storage, "2", "Boris")
    storage.teacher_links.add(student.id, me, primary=True)

    response = api.get(LINKS, headers=_auth())

    assert "primary" not in response.text
    assert response.json()["students"][0]["id"] == str(student.id)


def test_post_invite_is_idempotent_with_a_png_qr(api: TestClient, storage: InMemoryStorage) -> None:
    first = api.post(INVITE, json={}, headers=_auth())
    second = api.post(INVITE, json={"rotate": False}, headers=_auth())

    assert first.status_code == 200
    assert set(first.json()) == {"url", "qr"}
    assert _URL.fullmatch(first.json()["url"])
    assert second.json()["url"] == first.json()["url"]
    prefix, png = first.json()["qr"].split(",", 1)
    assert prefix == "data:image/png;base64"
    assert base64.b64decode(png).startswith(b"\x89PNG\r\n\x1a\n")


def test_rotating_changes_the_url(api: TestClient) -> None:
    first = api.post(INVITE, json={}, headers=_auth()).json()

    rotated = api.post(INVITE, json={"rotate": True}, headers=_auth()).json()
    kept = api.post(INVITE, json={}, headers=_auth()).json()

    assert _URL.fullmatch(rotated["url"])
    assert rotated["url"] != first["url"]
    assert rotated["qr"] != first["qr"]
    assert kept["url"] == rotated["url"]


def test_primary_returns_the_lists(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    first, second = _person(storage, "1"), _person(storage, "3")
    storage.teacher_links.add(me, first.id)
    storage.teacher_links.add(me, second.id)

    response = api.put(f"/api/v1/me/teachers/{second.id}/primary", headers=_auth())

    assert response.status_code == 200
    teachers = {t["id"]: t for t in response.json()["teachers"]}
    assert (teachers[str(second.id)]["primary"], teachers[str(second.id)]["primary_chosen"]) == (
        True,
        True,
    )
    assert (teachers[str(first.id)]["primary"], teachers[str(first.id)]["primary_chosen"]) == (
        False,
        False,
    )


def test_primary_of_someone_off_the_list_is_404(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    stranger = _person(storage, "1")

    response = api.put(f"/api/v1/me/teachers/{stranger.id}/primary", headers=_auth())

    assert (response.status_code, response.json()) == (404, {"code": "not_linked"})


def test_primary_race_is_409(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    teacher = _person(storage, "1")
    storage.teacher_links.add(me, teacher.id)
    storage.teacher_links.lose_next_flip = True

    response = api.put(f"/api/v1/me/teachers/{teacher.id}/primary", headers=_auth())

    assert (response.status_code, response.json()) == (409, {"code": "links_changed"})


@pytest.mark.parametrize("side", ["teachers", "students"])
def test_both_deletes_are_204_twice(api: TestClient, storage: InMemoryStorage, side: str) -> None:
    me = _me(api, storage)
    other = _person(storage, "1")
    if side == "teachers":
        storage.teacher_links.add(me, other.id)
    else:
        storage.teacher_links.add(other.id, me)
    url = f"/api/v1/me/{side}/{other.id}"

    first = api.delete(url, headers=_auth())
    second = api.delete(url, headers=_auth())

    assert (first.status_code, second.status_code) == (204, 204)
    assert storage.teacher_links.rows == {}


def test_a_foreign_id_deletes_nothing(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    teacher, student = _person(storage, "1"), _person(storage, "2")
    storage.teacher_links.add(student.id, teacher.id)

    by_teacher = api.delete(f"/api/v1/me/teachers/{teacher.id}", headers=_auth())
    by_student = api.delete(f"/api/v1/me/students/{student.id}", headers=_auth())

    assert (by_teacher.status_code, by_student.status_code) == (204, 204)
    assert storage.teacher_links.teachers_of(student.id) == [teacher.id]


@pytest.mark.parametrize("url", ["/api/v1/me/teachers/{id}", "/api/v1/me/students/{id}"])
def test_a_malformed_id_is_a_validation_error(api: TestClient, url: str) -> None:
    assert api.delete(url.format(id="not-a-uuid"), headers=_auth()).status_code == 422


def test_every_answer_is_no_store(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    teacher = _person(storage, "1")
    storage.teacher_links.add(me, teacher.id)

    answers = [
        api.get(LINKS, headers=_auth()),
        api.post(INVITE, json={}, headers=_auth()),
        api.put(f"/api/v1/me/teachers/{teacher.id}/primary", headers=_auth()),
        api.delete(f"/api/v1/me/teachers/{teacher.id}", headers=_auth()),
        api.delete(f"/api/v1/me/students/{teacher.id}", headers=_auth()),
    ]

    for answer in answers:
        assert answer.is_success, answer.request.url
        assert answer.headers["cache-control"] == "no-store", answer.request.url


def test_no_route_takes_a_code_in_its_path_or_query(api: TestClient) -> None:
    """Cloud Run logs URLs: the code rides in no URL we serve."""
    paths: dict[str, dict[str, dict[str, Any]]] = api.get("/openapi.json").json()["paths"]

    assert {LINKS, INVITE} <= paths.keys()
    assert "/api/v1/me/teachers/{id}/primary" in paths
    for path, operations in paths.items():
        assert "code" not in path.lower(), path
        if not re.search(r"/(links|invite|teachers|students)\b", path):
            continue
        for operation in operations.values():
            names = {p["name"] for p in operation.get("parameters", [])}
            assert names <= {"id", "Authorization"}, (path, names)


def test_the_invite_url_keeps_the_code_out_of_the_path(api: TestClient) -> None:
    link: str = api.post(INVITE, json={}, headers=_auth()).json()["url"]

    assert (urlsplit(link).netloc, urlsplit(link).path) == ("t.me", f"/{BOT}")


def test_the_invite_request_carries_only_rotate(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()

    body = schema["paths"][INVITE]["post"]["requestBody"]["content"]["application/json"]["schema"]
    ref = body.get("$ref") or next(a["$ref"] for a in body["anyOf"] if "$ref" in a)
    request = schema["components"]["schemas"][ref.rsplit("/", 1)[1]]
    assert set(request["properties"]) == {"rotate"}


def test_openapi_lists_the_error_codes(api: TestClient) -> None:
    codes = api.get("/openapi.json").json()["components"]["schemas"]["ErrorCode"]["enum"]

    assert {"not_linked", "links_changed"} <= set(codes)


def test_the_mini_apps_contract_has_the_routes() -> None:
    """The TS client is generated from this file: `npm run typecheck` builds against it."""
    path = Path(__file__).resolve().parents[3] / "miniapp" / "src" / "api" / "openapi.json"
    paths = json.loads(path.read_text())["paths"]

    assert {LINKS, INVITE, "/api/v1/me/teachers/{id}/primary"} <= paths.keys()
    assert "/api/v1/me/students/{id}" in paths


def test_an_empty_bot_username_never_builds_a_broken_link(storage: InMemoryStorage) -> None:
    """The spec only says "empty hides the invite in dev": the status is the adapter's call."""
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))

    with TestClient(create_app(settings, storage)) as client:
        response = client.post(INVITE, json={}, headers=_auth())

    assert not response.is_success
    assert "t.me" not in response.text


@pytest.mark.parametrize(("slug", "explicit"), [("mysuru", True), (None, False), ("almaty", True)])
def test_moon_location_keeps_an_explicit_mysuru(
    api: TestClient, slug: str | None, explicit: bool
) -> None:
    response = api.put("/api/v1/me/moon-location", json={"slug": slug}, headers=_auth())

    assert response.json() == {"slug": slug or "mysuru", "explicit": explicit}
