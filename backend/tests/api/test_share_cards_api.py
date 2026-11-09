"""ST-07 routes (spec §5, ADR-0040): `POST /api/v1/me/share-cards` (201 shape, union body,
404/422/429, 401 without initData, 503 when PUBLIC_API_URL is empty), `GET/HEAD
/share/v1/{token}.png` (no auth, a real PNG, cache and privacy headers, one 404 for
unknown/expired/malformed, not in OpenAPI, the token never logged), `POST …/{id}/send`
(the bot posts the photo once: 200, then 409). Clock frozen on Mon 9 Nov 2026, 03:00 UTC."""

import json
import logging
import time as wall
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FakeNotifier, InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.days import DayLog, DayStatus
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
PUBLIC = "https://tristhana-api-test.a.run.app"
URL = "/api/v1/me/share-cards"
PNG = b"\x89PNG\r\n\x1a\n"


def _auth(user_id: int = 42) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Ash", "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(wall.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


class Env:
    def __init__(self) -> None:
        self.storage = InMemoryStorage()
        self.storage.repo.clock.instant = NOW
        self.notifier = FakeNotifier()


def _client(env: Env, monkeypatch: pytest.MonkeyPatch, public: str = PUBLIC) -> TestClient:
    import tristhana.main

    class Frozen:
        def now(self) -> datetime:
            return NOW

    monkeypatch.setattr(tristhana.main, "SystemClock", Frozen)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        public_api_url=public,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings, env.storage, env.notifier))


@pytest.fixture
def env() -> Env:
    return Env()


@pytest.fixture
def api(env: Env, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with _client(env, monkeypatch) as client:
        yield client


def _me(api: TestClient, env: Env, practiced: int = 3) -> UUID:
    assert api.get("/api/v1/me", headers=_auth()).status_code == 200
    me = env.storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, "42")]
    env.storage.repo.accounts[me] = replace(env.storage.repo.accounts[me], timezone="Asia/Almaty")
    for i in range(practiced):
        day = date(2026, 10, 1) + timedelta(days=i)
        env.storage.day_repo.rows[(me, day)] = (DayLog(day, DayStatus.PRACTICED), None)
    return me


def _month(fmt: str = "story") -> dict[str, object]:
    return {"format": fmt, "card": {"kind": "month", "year": 2026, "month": 10}}


def test_create_returns_the_card_and_its_image(api: TestClient, env: Env) -> None:
    _me(api, env)
    r = api.post(URL, json=_month(), headers=_auth())
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"id", "image_url", "width", "height", "file_name", "expires_at"}
    assert (body["width"], body["height"]) == (1080, 1920)
    assert body["image_url"] == f"{PUBLIC}/share/v1/{body['id']}.png"
    assert body["file_name"] == "tristhana-2026-10-story.png"
    image = api.get(f"/share/v1/{body['id']}.png")  # no auth: the URL is the capability
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(PNG)
    assert image.headers["cache-control"] == "public, max-age=3600"
    assert "access-control-allow-origin" not in image.headers
    assert image.headers["x-content-type-options"] == "nosniff"
    head = api.head(f"/share/v1/{body['id']}.png")
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == str(len(image.content))


def test_year_square_card(api: TestClient, env: Env) -> None:
    _me(api, env)
    r = api.post(
        URL, json={"format": "square", "card": {"kind": "year", "year": 2026}}, headers=_auth()
    )
    assert r.status_code == 201
    assert (r.json()["width"], r.json()["height"]) == (1080, 1080)


def test_errors(api: TestClient, env: Env) -> None:
    assert api.post(URL, json=_month()).status_code == 401
    _me(api, env, practiced=0)
    future = {"format": "story", "card": {"kind": "month", "year": 2026, "month": 12}}
    assert api.post(URL, json=future, headers=_auth()).json()["code"] == "invalid_period"
    empty = api.post(URL, json=_month(), headers=_auth())
    assert (empty.status_code, empty.json()["code"]) == (422, "nothing_to_share")
    count = {"format": "story", "card": {"kind": "count", "count": 100}}
    assert api.post(URL, json=count, headers=_auth()).status_code == 404
    asana = {"format": "story", "card": {"kind": "asana", "event_id": 5}}
    assert api.post(URL, json=asana, headers=_auth()).status_code == 404
    bad = {"format": "poster", "card": {"kind": "year", "year": 2026}}
    assert api.post(URL, json=bad, headers=_auth()).status_code == 422


def test_rate_limited(api: TestClient, env: Env) -> None:
    _me(api, env)
    from tristhana.application.share_cards import DAILY_LIMIT

    for _ in range(DAILY_LIMIT):
        assert api.post(URL, json=_month("square"), headers=_auth()).status_code == 201
    r = api.post(URL, json=_month("square"), headers=_auth())
    assert (r.status_code, r.json()["code"]) == (429, "rate_limited")


def test_one_404_for_unknown_malformed_and_expired(api: TestClient, env: Env) -> None:
    _me(api, env)
    card = api.post(URL, json=_month(), headers=_auth()).json()
    for token in ("A" * 22, "nope", card["id"] + "x"):
        r = api.get(f"/share/v1/{token}.png")
        assert (r.status_code, r.content) == (404, b"Not found\n")
    env.storage.share_cards.rows.clear()
    assert api.get(f"/share/v1/{card['id']}.png").status_code == 404


def test_off_without_a_public_url(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(env, monkeypatch, public="") as api:
        _me(api, env)
        r = api.post(URL, json=_month(), headers=_auth())
        assert (r.status_code, r.json()["code"]) == (503, "unavailable")


def test_send_to_my_chat_once(api: TestClient, env: Env) -> None:
    _me(api, env)
    card = api.post(URL, json=_month(), headers=_auth()).json()
    r = api.post(f"{URL}/{card['id']}/send", headers=_auth())
    assert r.json() == {"sent": True}
    ((recipient, png),) = env.notifier.cards
    assert recipient.telegram_id == "42"
    assert png.startswith(PNG)
    again = api.post(f"{URL}/{card['id']}/send", headers=_auth())
    assert (again.status_code, again.json()["code"]) == (409, "already_sent")


def test_send_when_the_bot_is_blocked(api: TestClient, env: Env) -> None:
    _me(api, env)
    card = api.post(URL, json=_month(), headers=_auth()).json()
    env.notifier.card_outcomes.append(DeliveryResult(DeliveryStatus.BLOCKED))
    r = api.post(f"{URL}/{card['id']}/send", headers=_auth())
    assert (r.status_code, r.json()["code"]) == (409, "bot_unreachable")
    assert api.post(f"{URL}/nope/send", headers=_auth()).status_code == 404


def test_image_route_is_not_in_openapi_but_the_api_is(api: TestClient) -> None:
    paths = api.get("/openapi.json").json()["paths"]
    assert not any(p.startswith("/share/") for p in paths)
    assert URL in paths
    assert f"{URL}/{{card_id}}/send" in paths


def test_token_never_logged(api: TestClient, env: Env, caplog: pytest.LogCaptureFixture) -> None:
    from tristhana.logs import MaskFeedTokens

    _me(api, env)
    card = api.post(URL, json=_month(), headers=_auth()).json()
    caplog.set_level(logging.DEBUG)
    api.get(f"/share/v1/{card['id']}x.png")
    record = logging.LogRecord(
        "x", logging.INFO, "", 0, f'"GET /share/v1/{card["id"]}.png"', None, None
    )
    MaskFeedTokens().filter(record)
    assert card["id"] not in record.getMessage()
    assert card["id"] not in caplog.text
