"""SC-06 routes (spec §4, §7, §8; ADR-0036).

`GET/POST/DELETE /api/v1/me/calendar-feed`: initData (401 without), `no-store`, the exact
key set of `CalendarFeedOut` (absent values are null), create = rotate, DELETE idempotent 204,
URLs built from `PUBLIC_API_URL` (empty: `on` and `available` false). `GET`/`HEAD
/ical/v1/{token}.ics`: `text/calendar; charset=utf-8`, an ETag of the body (16 hex of its
SHA-256) and 304 on `If-None-Match`, the cache and privacy headers, no CORS, not in OpenAPI;
one identical 404 for malformed, unknown, rotated, revoked and deleted. `/ical/v1/{token}/
subscribe`: 302 to `webcal://` with no read. No log, rest, check-in or diary port is touched
by a poll (those fakes are down). The token never reaches a log line; our line carries
`sha256(token)[:8]`.

Assumed: the setting is `Settings.public_api_url`, https only. The clock is frozen on Mon 9
Nov 2026, 08:00 in Almaty."""

import hashlib
import json
import logging
import re
import time as wall
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.api.initdata import sign
from tristhana.application.ports.classes import StoredClass
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.classes import ClassType
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
PUBLIC = "https://tristhana-api-test.a.run.app"
HOST = "tristhana-api-test.a.run.app"
ORIGIN = "https://tristhana.web.app"
URL = "/api/v1/me/calendar-feed"
FEED_KEYS = {"on", "available", "url", "google_url", "subscribe_url", "created_at", "fetched_on"}
MYSORE = UUID("5c000000-0000-4000-8000-0000000000a1")
UNKNOWN = "Zz9yX8wV7uT6sR5qP4oN3mL2kJ1iH0gF9eD8cB7aA6_"
ICS = re.compile(r"/ical/v1/([A-Za-z0-9_-]{43})\.ics")


def _auth(user_id: int = ME_TG, name: str = "Ash") -> dict[str, str]:
    profile = {"id": user_id, "first_name": name, "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(wall.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    storage = shala_storage()
    storage.repo.clock.instant = NOW
    return storage


def _client(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch, public: str = PUBLIC
) -> TestClient:
    import tristhana.main

    class Frozen:
        def now(self) -> datetime:
            return NOW

    monkeypatch.setattr(tristhana.main, "SystemClock", Frozen)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
        cors_origins=ORIGIN,
        public_api_url=public,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings, storage))


@pytest.fixture
def api(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with _client(storage, monkeypatch) as client:
        yield client


def _me(api: TestClient, storage: InMemoryStorage) -> UUID:
    assert api.get("/api/v1/me", headers=_auth()).status_code == 200
    me = storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, str(ME_TG))]
    storage.repo.accounts[me] = replace(storage.repo.accounts[me], timezone="Asia/Almaty")
    return me


def _member_with_a_class(storage: InMemoryStorage, me: UUID) -> None:
    anna = person(storage, "1001", "Anna")
    shala = storage.shalas.add_shala(anna.id, name="Ashtanga Almaty").id
    storage.shalas.add_student(shala, me)
    storage.schedule.classes[MYSORE] = (
        shala,
        StoredClass(
            id=MYSORE, type=ClassType.MYSORE, title=None, online=False, city=None,
            teacher_id=anna.id, start=time(6, 0), minutes=150,
            weekdays=frozenset({1, 2, 3, 4, 5}), every=1, starts_on=date(2026, 9, 1),
            ends_on=None,
        ),
    )  # fmt: skip
    storage.moon_repo.days_by_location["almaty"] = [
        MoonDay(date(2026, 11, 24), MoonDayKind.PURNIMA)
    ]


def _create(api: TestClient) -> dict[str, Any]:
    response = api.post(URL, headers=_auth())
    assert response.status_code == 200, response.text
    return response.json()


def _token(out: dict[str, Any]) -> str:
    found = ICS.search(out["url"])
    assert found is not None, out["url"]
    return found.group(1)


def _ics(token: str) -> str:
    return f"/ical/v1/{token}.ics"


# Auth and shapes


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_the_management_routes_need_init_data(api: TestClient, method: str) -> None:
    assert api.request(method, URL).status_code == 401
    assert api.post(f"{URL}/rotate").status_code == 401


def test_off_until_created(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)

    response = api.get(URL, headers=_auth())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    out = response.json()
    assert set(out) == FEED_KEYS
    assert (out["on"], out["available"]) == (False, True)
    assert all(out[k] is None for k in FEED_KEYS - {"on", "available"})


def test_create_returns_the_urls(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)

    response = api.post(URL, headers=_auth())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    out = response.json()
    assert set(out) == FEED_KEYS
    assert (out["on"], out["available"]) == (True, True)
    token = _token(out)
    assert out["url"] == f"{PUBLIC}/ical/v1/{token}.ics"
    assert out["subscribe_url"] == f"{PUBLIC}/ical/v1/{token}/subscribe"
    google = urlsplit(str(out["google_url"]))
    assert (google.scheme, google.netloc, google.path) == (
        "https",
        "calendar.google.com",
        "/calendar/r",
    )
    assert parse_qs(google.query)["cid"] == [f"webcal://{HOST}/ical/v1/{token}.ics"]
    assert datetime.fromisoformat(out["created_at"].replace("Z", "+00:00")) == NOW
    assert out["fetched_on"] is None
    assert api.get(URL, headers=_auth()).json() == out  # shown again (sealed copy, Q149)


def test_post_again_keeps_the_link(api: TestClient, storage: InMemoryStorage) -> None:
    """Review fix: a stale "Create" never breaks a subscribed calendar."""
    _me(api, storage)
    first = _create(api)

    again = _create(api)

    assert again == first
    assert api.get(_ics(_token(first))).status_code == 200


def test_rotate_replaces_the_link(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    old = _token(_create(api))

    response = api.post(f"{URL}/rotate", headers=_auth())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    new = _token(response.json())
    assert new != old
    assert api.get(_ics(old)).status_code == 404
    assert api.get(_ics(new)).status_code == 200


def _rotate(api: TestClient) -> dict[str, Any]:
    response = api.post(f"{URL}/rotate", headers=_auth())
    assert response.status_code == 200, response.text
    return response.json()


def test_delete_turns_it_off_and_is_idempotent(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    token = _token(_create(api))

    first = api.delete(URL, headers=_auth())
    second = api.delete(URL, headers=_auth())

    assert (first.status_code, second.status_code) == (204, 204)
    assert api.get(_ics(token)).status_code == 404
    assert api.get(URL, headers=_auth()).json()["on"] is False


def test_someone_else_sees_only_their_own(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    mine = _create(api)

    theirs = api.get(URL, headers=_auth(user_id=77, name="Other")).json()

    assert theirs["on"] is False
    assert theirs["url"] is None
    assert api.delete(URL, headers=_auth(user_id=77, name="Other")).status_code == 204
    assert api.get(_ics(_token(mine))).status_code == 200


def test_fetched_on_shows_after_a_poll(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    token = _token(_create(api))

    api.get(_ics(token))

    assert api.get(URL, headers=_auth()).json()["fetched_on"] == "2026-11-09"


def test_without_a_public_url_the_feature_is_hidden(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client(storage, monkeypatch, public="") as api:
        _me(api, storage)

        out = api.get(URL, headers=_auth()).json()

    assert (out["on"], out["available"]) == (False, False)
    assert out["url"] is None


def test_without_a_public_url_no_feed_is_served(
    storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fix: an empty PUBLIC_API_URL turns the feature off, not only its buttons."""
    with _client(storage, monkeypatch) as api:
        _me(api, storage)
        token = _token(_create(api))
    with _client(storage, monkeypatch, public="") as api:
        assert api.get(_ics(token)).status_code == 404
        assert api.get(f"/ical/v1/{token}/subscribe", follow_redirects=False).status_code == 404


def test_the_public_url_must_be_https() -> None:
    with pytest.raises(ValueError, match="public_api_url"):
        Settings(public_api_url="http://tristhana.example")  # pyright: ignore[reportCallIssue]
    assert Settings().public_api_url == ""  # pyright: ignore[reportAttributeAccessIssue]


# The feed


def test_the_feed(api: TestClient, storage: InMemoryStorage) -> None:
    me = _me(api, storage)
    _member_with_a_class(storage, me)
    token = _token(_create(api))

    response = api.get(_ics(token))

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["cache-control"] == "private, max-age=1800"
    assert response.headers["content-disposition"] == 'inline; filename="tristhana.ics"'
    assert response.headers["x-robots-tag"] == "noindex"
    assert response.headers["referrer-policy"] == "no-referrer"
    body = response.content
    assert body.startswith(b"BEGIN:VCALENDAR\r\n")
    assert body.endswith(b"END:VCALENDAR\r\n")
    assert f"UID:{MYSORE}-20261109@tristhana".encode() in body
    assert b"DTSTART:20261109T010000Z" in body
    assert b"DTSTART;VALUE=DATE:20261124" in body
    assert response.headers["etag"].strip('"') == hashlib.sha256(body).hexdigest()[:16]


def test_the_same_content_gives_the_same_body_and_etag(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """The first poll stamps `fetched_on`; that is not in the body."""
    me = _me(api, storage)
    _member_with_a_class(storage, me)
    token = _token(_create(api))

    first, second = api.get(_ics(token)), api.get(_ics(token))

    assert first.content == second.content
    assert first.headers["etag"] == second.headers["etag"]


def test_a_matching_if_none_match_is_304(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    token = _token(_create(api))
    etag = api.get(_ics(token)).headers["etag"]

    response = api.get(_ics(token), headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == etag
    stale = api.get(_ics(token), headers={"If-None-Match": '"0000000000000000"'})
    assert stale.status_code == 200


def test_head_has_the_get_headers_without_a_body(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    token = _token(_create(api))

    got, head = api.get(_ics(token)), api.head(_ics(token))

    assert head.status_code == 200
    assert head.content == b""
    for name in ("content-type", "etag", "cache-control", "content-disposition", "x-robots-tag"):
        assert head.headers[name] == got.headers[name], name


def test_the_feed_has_no_cors(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    token = _token(_create(api))

    response = api.get(_ics(token), headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert (
        api.get("/api/v1/health", headers={"Origin": ORIGIN}).headers["access-control-allow-origin"]
        == ORIGIN
    )  # CORS is on for the API: the absence above is the route's


def test_the_feed_is_not_in_openapi(api: TestClient) -> None:
    paths = api.get("/openapi.json").json()["paths"]

    assert not [p for p in paths if p.startswith("/ical")]
    assert "/api/v1/me/calendar-feed" in paths


def test_a_poll_touches_no_log_rest_or_private_data(
    api: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(api, storage)
    _member_with_a_class(storage, me)
    token = _token(_create(api))
    storage.day_repo.down = True  # the log, check-ins, diary, progression
    storage.rest_periods.down = True

    response = api.get(_ics(token))

    assert response.status_code == 200
    assert b"VEVENT" in response.content


# One 404 for every dead link


def _not_found(response: Any) -> tuple[int, bytes, dict[str, str]]:
    return response.status_code, response.content, dict(response.headers)


def test_every_dead_link_is_the_same_404(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    rotated = _token(_create(api))
    current = _token(_rotate(api))  # rotates `rotated` away
    malformed = [api.get(_ics("short")), api.get(_ics(UNKNOWN + "+")), api.get("/ical/v1/x.ics")]
    unknown = api.get(_ics(UNKNOWN))
    old = api.get(_ics(rotated))
    api.delete(URL, headers=_auth())
    revoked = api.get(_ics(current))

    responses = [*malformed, unknown, old, revoked]

    first = _not_found(responses[0])
    assert first[0] == 404
    assert b"VCALENDAR" not in first[1]
    for response in responses[1:]:
        assert _not_found(response) == first


def test_a_deleted_account_is_the_same_404(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    token = _token(_create(api))
    reference = _not_found(api.get(_ics(UNKNOWN)))

    deleted = api.request(
        "DELETE", "/api/v1/me", json={"confirm": "delete-everything"}, headers=_auth()
    )

    assert deleted.status_code == 204
    assert _not_found(api.get(_ics(token))) == reference


def test_a_malformed_token_reads_nothing(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    _create(api)
    storage.calendar_feed.calls.clear()

    for path in (_ics("short"), _ics("A" * 44), _ics("A" * 42 + "="), "/ical/v1/%2e%2e.ics"):
        assert api.get(path).status_code == 404

    assert storage.calendar_feed.calls == []


# The redirect for Apple and Outlook


def test_subscribe_redirects_to_webcal(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    token = _token(_create(api))
    storage.calendar_feed.calls.clear()

    response = api.get(f"/ical/v1/{token}/subscribe", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == f"webcal://{HOST}/ical/v1/{token}.ics"
    assert storage.calendar_feed.calls == []  # no read


def test_subscribe_refuses_a_malformed_token_and_is_not_cached(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """Review fix: no arbitrary path text in a webcal:// target; the redirect isn't cached."""
    _me(api, storage)
    token = _token(_create(api))
    reference = _not_found(api.get(_ics(UNKNOWN)))

    bad = api.get("/ical/v1/not-a-token/subscribe", follow_redirects=False)
    good = api.get(f"/ical/v1/{token}/subscribe", follow_redirects=False)

    assert _not_found(bad) == reference
    assert good.headers["cache-control"] == "no-store"
    assert good.headers["referrer-policy"] == "no-referrer"


def test_a_weak_etag_still_matches(api: TestClient, storage: InMemoryStorage) -> None:
    _me(api, storage)
    token = _token(_create(api))
    etag = api.get(_ics(token)).headers["etag"]

    assert api.get(_ics(token), headers={"If-None-Match": f"W/{etag}"}).status_code == 304


def test_subscribe_with_a_dead_token_is_still_a_redirect(api: TestClient) -> None:
    response = api.get(f"/ical/v1/{UNKNOWN}/subscribe", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == f"webcal://{HOST}/ical/v1/{UNKNOWN}.ics"


# Logs (spec §7, Q153)


class _Everything(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(("httpx", "httpcore")):  # the test client's own lines
            return
        self.lines.append(f"{self.format(record)} {record.args!r} {record.__dict__!r}")


@pytest.fixture
def logs(api: TestClient) -> Iterator[list[str]]:
    """Every logger at DEBUG into one handler. After `api`: building the app replaces the
    root handlers (pytest's caplog handler included)."""
    handler = _Everything()
    root = logging.getLogger()
    named = [
        logger
        for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    ]
    levels = [(logger, logger.level) for logger in [root, *named]]
    root.addHandler(handler)
    for logger, _ in levels:
        logger.setLevel(logging.DEBUG)
    yield handler.lines
    root.removeHandler(handler)
    for logger, level in levels:
        logger.setLevel(level)


def test_the_token_never_reaches_a_log(
    api: TestClient, storage: InMemoryStorage, logs: list[str]
) -> None:
    me = _me(api, storage)
    _member_with_a_class(storage, me)
    token = _token(_create(api))
    api.get(URL, headers=_auth())

    api.get(_ics(token))
    api.head(_ics(token))
    api.get(f"/ical/v1/{token}/subscribe", follow_redirects=False)
    _rotate(api)  # the old one is now dead
    api.get(_ics(token))

    assert [line for line in logs if token in line] == []
    prefix = hashlib.sha256(token.encode()).hexdigest()[:8]
    assert any(prefix in line for line in logs), "our line per fetch carries the hash prefix"
