"""NT-03 routes (spec §4, §8; ADR-0038): initData (401 without), `no-store` on every answer,
the exact key sets, 201/403/404/409/422 per §4, a non-member 404 equal to an unknown id,
moderation by a shala manager, idempotent mute and delete, the `notification-settings`
partial write of `announcements`, and `ShalaMeOut.announce`. The clock is frozen."""

import json
import time as wall
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.announcement_fakes import Person
from tests.fakes import FixedClock, InMemoryStorage
from tests.shala_fakes import shala_storage
from tristhana.api.initdata import sign
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.shalas import ShalaRole
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
NOW = datetime(2026, 11, 9, 5, 0, tzinfo=UTC)
ME_TG = 42
URL = "/api/v1/me/announcements"
SENT_KEYS = {"id", "source", "text", "created_at", "pinned_until", "audience"}
ITEM_KEYS = {"id", "source", "author_name", "text", "created_at", "pinned_until", "can_manage"}


def _auth(user_id: int = ME_TG, name: str = "Ash") -> dict[str, str]:
    profile = {"id": user_id, "first_name": name, "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(wall.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    storage = shala_storage()
    storage.repo.clock.instant = NOW
    storage.announcements.clock = FixedClock(NOW)
    return storage


@pytest.fixture
def api(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    import tristhana.main

    class Frozen:
        def now(self) -> datetime:
            return NOW

    monkeypatch.setattr(tristhana.main, "SystemClock", Frozen)
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage)) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage, tg: int = ME_TG, name: str = "Ash") -> UUID:
    assert api.get("/api/v1/me", headers=_auth(tg, name)).status_code == 200
    me = storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(tg))]
    storage.announcements.people.setdefault(me, Person(name))
    return me


def _no_store(response: Any) -> None:
    assert response.headers["cache-control"] == "no-store", response.headers


def test_401_without_init_data(api: TestClient) -> None:
    assert api.get(URL).status_code == 401
    assert api.post(URL, json={"to": "students", "text": "x"}).status_code == 401


def test_a_teacher_sends_to_their_students(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    repo = storage.announcements
    student = repo.person("Bea")
    repo.link(student, me)
    response = api.post(
        URL,
        headers=_auth(),
        json={"to": "students", "text": "  Led class Sun 15 Nov, 7:00  ", "pin_days": 7},
    )
    assert response.status_code == 201, response.text
    _no_store(response)
    body = response.json()
    assert set(body) == SENT_KEYS
    assert body["text"] == "Led class Sun 15 Nov, 7:00"
    assert body["audience"] == 1
    assert body["source"] == {"kind": "teacher", "id": str(me), "name": "Ash"}
    assert body["pinned_until"].startswith("2026-11-16")
    sent = api.get(f"{URL}/sent", headers=_auth())
    _no_store(sent)
    assert [s["id"] for s in sent.json()] == [body["id"]]


@pytest.mark.parametrize(
    "payload",
    [
        {"to": "students", "text": ""},
        {"to": "students", "text": "a" * 1001},
        {"to": "students", "text": "ok", "pin_days": 14},
        {"to": "shala", "text": "ok"},
        {"to": "students", "text": "ok", "shala_id": str(uuid4())},
    ],
)
def test_422(api: TestClient, storage: InMemoryStorage, payload: dict[str, Any]) -> None:
    me = _me(api, storage)
    storage.announcements.link(storage.announcements.person("Bea"), me)
    response = api.post(URL, headers=_auth(), json=payload)
    assert response.status_code == 422
    if response.json().get("code"):
        assert response.json()["code"] in ("invalid_announcement",)


def test_no_students_is_422(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    response = api.post(URL, headers=_auth(), json={"to": "students", "text": "hello"})
    assert (response.status_code, response.json()) == (422, {"code": "invalid_announcement"})
    _no_store(response)


def test_the_fourth_is_409(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    storage.announcements.link(storage.announcements.person("Bea"), me)
    for i in range(3):
        ok = api.post(URL, headers=_auth(), json={"to": "students", "text": f"n{i}"})
        assert ok.status_code == 201
    response = api.post(URL, headers=_auth(), json={"to": "students", "text": "fourth"})
    assert (response.status_code, response.json()) == (409, {"code": "announcement_limit"})
    _no_store(response)


def test_shala_roles_404_and_403(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    repo = storage.announcements
    owner = repo.person("Owner")
    shala = repo.shala("Ashtanga Almaty", owner)
    unknown = api.post(
        URL, headers=_auth(), json={"to": "shala", "shala_id": str(uuid4()), "text": "hi"}
    )
    outsider = api.post(
        URL, headers=_auth(), json={"to": "shala", "shala_id": str(shala), "text": "hi"}
    )
    assert unknown.status_code == outsider.status_code == 404
    assert unknown.json() == outsider.json() == {"code": "not_found"}
    repo.staff(shala, me, ShalaRole.ASSISTANT)
    forbidden = api.post(
        URL, headers=_auth(), json={"to": "shala", "shala_id": str(shala), "text": "hi"}
    )
    assert (forbidden.status_code, forbidden.json()) == (403, {"code": "not_allowed"})
    repo.staff(shala, me, ShalaRole.OFFICE)
    ok = api.post(URL, headers=_auth(), json={"to": "shala", "shala_id": str(shala), "text": "hi"})
    assert ok.status_code == 201
    assert ok.json()["source"] == {"kind": "shala", "id": str(shala), "name": "Ashtanga Almaty"}
    assert ok.json()["audience"] == 1


def test_the_feed(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    repo = storage.announcements
    teacher = repo.person("Anna")
    repo.link(me, teacher)
    repo.clock.instant = NOW
    from tristhana.application.announcements import Target
    from tristhana.application.policies import Principal
    from tristhana.domain.accounts import Account

    async def send() -> None:
        from tristhana.application.announcements import SendAnnouncement

        anna = Account(teacher, "Anna", "en", "Asia/Almaty", NOW)
        await SendAnnouncement(repo, FixedClock(NOW)).execute(
            Principal(anna), Target(), "Closed Mon 10 Nov", 7
        )

    import asyncio

    asyncio.run(send())
    response = api.get(URL, headers=_auth())
    _no_store(response)
    body = response.json()
    assert set(body) == {"items", "sources", "more"}
    [item] = body["items"]
    assert set(item) == ITEM_KEYS
    assert item["author_name"] == "Anna"
    assert item["can_manage"] is False
    assert item["pinned_until"] is not None
    assert body["sources"] == [
        {"kind": "teacher", "id": str(teacher), "name": "Anna", "muted": False}
    ]
    one = api.get(URL, headers=_auth(), params={"kind": "teacher", "id": str(teacher)})
    assert one.status_code == 200
    foreign = api.get(URL, headers=_auth(), params={"kind": "teacher", "id": str(uuid4())})
    assert (foreign.status_code, foreign.json()) == (404, {"code": "not_found"})
    _no_store(foreign)
    half = api.get(URL, headers=_auth(), params={"kind": "teacher"})
    assert half.status_code == 422


def test_mute_is_idempotent_and_404_for_strangers(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    repo = storage.announcements
    teacher = repo.person("Anna")
    repo.link(me, teacher)
    url = f"/api/v1/me/announcement-mutes/teacher/{teacher}"
    for _ in range(2):
        response = api.put(url, headers=_auth(), json={"muted": True})
        assert response.status_code == 204
        _no_store(response)
    assert repo.links[(me, teacher)].muted
    stranger = api.put(
        f"/api/v1/me/announcement-mutes/shala/{uuid4()}", headers=_auth(), json={"muted": True}
    )
    assert stranger.status_code == 404


def test_a_manager_moderates_and_a_teacher_cannot(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    repo = storage.announcements
    owner, desk, s = repo.person("O"), repo.person("Desk"), repo.person("S")
    shala = repo.shala("Ashtanga Almaty", owner)
    repo.staff(shala, desk, ShalaRole.OFFICE)
    repo.student(shala, s)
    repo.staff(shala, me, ShalaRole.TEACHER)
    import asyncio

    from tristhana.application.ports.announcements import NewAnnouncement
    from tristhana.domain.announcements import Source, SourceKind

    posted = asyncio.run(
        repo.create(NewAnnouncement(desk, Source(SourceKind.SHALA, shala), "hello", None, NOW, 3))
    )
    assert posted.item is not None
    item = posted.item.id
    denied = api.delete(f"{URL}/{item}", headers=_auth())
    assert (denied.status_code, denied.json()) == (403, {"code": "not_allowed"})
    pin = api.patch(f"{URL}/{item}", headers=_auth(), json={"pin_days": 7})
    assert pin.status_code == 403
    repo.staff(shala, me, ShalaRole.ADMIN)
    pinned = api.patch(f"{URL}/{item}", headers=_auth(), json={"pin_days": 30})
    assert pinned.status_code == 200, pinned.text
    assert set(pinned.json()) == SENT_KEYS
    for _ in range(2):
        gone = api.delete(f"{URL}/{item}", headers=_auth())
        assert gone.status_code == 204
        _no_store(gone)
    unknown = api.patch(f"{URL}/{uuid4()}", headers=_auth(), json={"pin_days": 0})
    assert (unknown.status_code, unknown.json()) == (404, {"code": "not_found"})


def test_the_settings_switch(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    settings = "/api/v1/me/notification-settings"
    assert api.get(settings, headers=_auth()).json()["announcements"] is True
    off = api.patch(settings, headers=_auth(), json={"announcements": False})
    assert off.status_code == 200, off.text
    assert off.json()["announcements"] is False
    other = api.patch(settings, headers=_auth(), json={"daily_cap": 2})
    assert other.json()["announcements"] is False  # a partial write keeps it
    back = api.patch(settings, headers=_auth(), json={"announcements": None})
    assert back.json()["announcements"] is True


def test_the_shala_card_says_who_may_announce(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    shalas = storage.shalas
    owner = storage.repo.accounts[me]
    created = shalas.add_shala(owner.id, name="Ashtanga Almaty")
    card = api.get(f"/api/v1/shalas/{created.id}", headers=_auth())
    assert card.status_code == 200, card.text
    assert card.json()["me"]["announce"] is True
