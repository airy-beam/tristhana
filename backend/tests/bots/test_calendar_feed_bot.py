"""The calendar subscription through the real webhook (SC-06 spec §2, §5, §8; ADR-0036,
ADR-0008). Callbacks `c1:f:<a>`: `s` show, `n` create, `r`/`R` rotate ask/confirm, `x`/`X`
off ask/confirm; anything else is ignored. The screen off and on, in EN and RU; the link
posted in my own chat with the 🔒 line (Q151) as plain text (no `parse_mode`); the Google
`cid=` and Apple/Outlook `/subscribe` URL buttons, https only (Q152); "Join a shala" for
someone without one (Q146); a stale `R`/`X` acts on the current link only; answered first,
edited in place; every datum ≤ 12 bytes. Entry rows on `/schedule`, `/moon` and `/settings`;
none without `PUBLIC_API_URL`. Real use cases over the in-memory ports.

The clock is frozen on Mon 9 Nov 2026, 08:00 in Almaty."""

import itertools
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.domain.accounts import Account
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
PUBLIC = "https://tristhana-api-test.a.run.app"
HOST = "tristhana-api-test.a.run.app"
FEED_URL = re.compile(re.escape(PUBLIC) + r"/ical/v1/([A-Za-z0-9_-]{43})\.ics")
_ids = itertools.count(360_000)


@dataclass
class Sent:
    name: str
    fields: dict[str, Any]


@dataclass
class Frozen:
    instant: datetime = NOW

    def now(self) -> datetime:
        return self.instant


@pytest.fixture
def storage() -> InMemoryStorage:
    storage = shala_storage()
    storage.repo.clock.instant = NOW
    return storage


@pytest.fixture
def outbound(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> list[Sent]:
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        sent.append(Sent(method.__api_method__, method.model_dump()))
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


def _app(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch, public: str) -> TestClient:
    import tristhana.main

    monkeypatch.setattr(tristhana.main, "SystemClock", Frozen)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url="https://tristhana.web.app",
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
        public_api_url=public,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings, storage))


@pytest.fixture
def client(
    storage: InMemoryStorage, outbound: list[Sent], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    with _app(storage, monkeypatch, PUBLIC) as c:
        yield c


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str) -> dict[str, Any]:
    return {"id": ME_TG, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _command(client: TestClient, text: str, lang: str = "en") -> Any:
    message = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": ME_TG, "type": "private"},
        "from": _user(lang),
        "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str, lang: str = "en") -> Any:
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": ME_TG, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang),
        "chat_instance": "ci",
        "data": data,
        "message": message | {"text": "…"},
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _buttons(body: Any) -> list[dict[str, Any]]:
    if not body:
        return []
    return [b for row in body.get("reply_markup", {}).get("inline_keyboard", []) for b in row]


def _datas(body: Any) -> list[str]:
    return [b["callback_data"] for b in _buttons(body) if "callback_data" in b]


def _urls(body: Any) -> list[str]:
    return [b["url"] for b in _buttons(body) if "url" in b]


def _flat(text: str) -> str:
    return " ".join(text.replace("⁨", "").replace("⁩", "").split())


def _t(key: str, locale: str = "en", **args: Any) -> str:
    return _flat(FluentTranslator().t(locale, key, **args))  # type: ignore[arg-type]


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Account:
    _command(client, "/start", lang)
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    storage.repo.accounts[me.id] = replace(me, timezone="Asia/Almaty")
    return storage.repo.accounts[me.id]


def _join(storage: InMemoryStorage, me: Account) -> None:
    anna = person(storage, "1001", "Anna")
    shala = storage.shalas.add_shala(anna.id, name="Ashtanga Almaty").id
    storage.shalas.add_student(shala, me.id)


def _messages(body: Any, outbound: list[Sent]) -> list[dict[str, Any]]:
    """Every message the tap produced: the webhook reply and any sent call."""
    out = [body] if body else []
    out += [s.fields for s in outbound if s.name in ("sendMessage", "editMessageText")]
    return out


def _link_message(body: Any, outbound: list[Sent]) -> dict[str, Any]:
    found = [m for m in _messages(body, outbound) if FEED_URL.search(m.get("text") or "")]
    assert found, "no message carries the link"
    return found[-1]


def _token(message: dict[str, Any]) -> str:
    found = FEED_URL.search(message["text"])
    assert found is not None
    return found.group(1)


# The screen


def test_off_in_english(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _join(storage, me)

    body = _tap(client, "c1:f:s")

    assert body["method"] == "editMessageText"
    assert body.get("parse_mode") is None
    text = _flat(body["text"])
    assert text.startswith(_t("feed-title"))
    assert _t("feed-explain") in text
    assert _t("feed-moon-only") not in text
    assert _datas(body) == ["c1:f:n"]
    assert [b["text"] for b in _buttons(body)] == ["📅 Create my link"]
    assert FEED_URL.search(body["text"]) is None


def test_off_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    _join(storage, me)

    body = _tap(client, "c1:f:s", "ru")

    text = _flat(body["text"])
    assert text.startswith("📅 Подписка в календаре")
    assert _t("feed-explain", "ru") in text
    assert [b["text"] for b in _buttons(body)] == ["📅 Создать ссылку"]


def test_without_a_shala_it_says_moon_days_alone(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)

    body = _tap(client, "c1:f:s")

    assert _t("feed-moon-only") in _flat(body["text"])
    assert _datas(body) == ["c1:f:n"]


def test_create_posts_the_link_in_my_chat(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    _join(storage, me)
    outbound.clear()

    body = _tap(client, "c1:f:n")

    assert outbound[0].name == "answerCallbackQuery"
    message = _link_message(body, outbound)
    assert message["chat_id"] == ME_TG
    assert message.get("parse_mode") is None
    text = _flat(message["text"])
    assert _t("feed-private") in text
    assert _t("feed-checked", day="none") in text  # "Not used by a calendar yet"
    token = _token(message)
    assert storage.calendar_feed.token_of(me.id) == token
    assert client.get(f"/ical/v1/{token}.ics").status_code == 200


def test_the_on_screen_buttons(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _join(storage, me)
    _tap(client, "c1:f:n")
    token = storage.calendar_feed.token_of(me.id)

    body = _tap(client, "c1:f:s")

    assert _token(body) == token
    urls = _urls(body)
    assert all(u.startswith("https://") for u in urls)
    assert not any(u.startswith("webcal:") for u in urls)
    google = next(u for u in urls if "calendar.google.com" in u)
    assert parse_qs(urlsplit(google).query)["cid"] == [f"webcal://{HOST}/ical/v1/{token}.ics"]
    assert f"{PUBLIC}/ical/v1/{token}/subscribe" in urls
    by_text = {b["text"]: b for b in _buttons(body)}
    assert by_text["Add to Google Calendar"]["url"] == google
    assert by_text["Add to Apple / Outlook"]["url"] == f"{PUBLIC}/ical/v1/{token}/subscribe"
    assert set(_datas(body)) == {"c1:f:r", "c1:f:x"}
    assert "c1:f:n" not in _datas(body)


def test_the_on_screen_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    _join(storage, me)
    _tap(client, "c1:f:n", "ru")

    body = _tap(client, "c1:f:s", "ru")

    text = _flat(body["text"])
    assert _t("feed-private", "ru") in text
    assert _t("feed-checked", "ru", day="none") in text
    texts = {b["text"] for b in _buttons(body)}
    assert {"Добавить в Google Календарь", "Добавить в Apple / Outlook"} <= texts


def test_the_last_poll_date_shows(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _tap(client, "c1:f:n")
    token = storage.calendar_feed.token_of(me.id)
    assert client.get(f"/ical/v1/{token}.ics").status_code == 200

    body = _tap(client, "c1:f:s")

    text = _flat(body["text"])
    assert _t("feed-checked", day="none") not in text
    assert "Last checked by a calendar:" in text


# Rotate and turn off, with a confirm step


def test_rotate_asks_first(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _tap(client, "c1:f:n")
    old = storage.calendar_feed.token_of(me.id)

    ask = _tap(client, "c1:f:r")

    assert _t("feed-rotate-confirm") in _flat(ask["text"])
    assert "c1:f:R" in _datas(ask)
    assert storage.calendar_feed.token_of(me.id) == old  # nothing changed yet


def test_rotate_confirmed(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    _tap(client, "c1:f:n")
    old = storage.calendar_feed.token_of(me.id)
    outbound.clear()

    body = _tap(client, "c1:f:R")

    new = storage.calendar_feed.token_of(me.id)
    assert new is not None
    assert new != old
    message = _link_message(body, outbound)
    assert _token(message) == new
    assert _t("feed-private") in _flat(message["text"])
    assert client.get(f"/ical/v1/{old}.ics").status_code == 404
    assert client.get(f"/ical/v1/{new}.ics").status_code == 200


def test_turn_off_asks_first_then_turns_off(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _tap(client, "c1:f:n")
    token = storage.calendar_feed.token_of(me.id)

    ask = _tap(client, "c1:f:x")
    assert _t("feed-off-confirm") in _flat(ask["text"])
    assert "c1:f:X" in _datas(ask)
    assert storage.calendar_feed.token_of(me.id) == token

    done = _tap(client, "c1:f:X")

    assert storage.calendar_feed.token_of(me.id) is None
    assert _t("feed-off-done") in _flat(done["text"])
    assert client.get(f"/ical/v1/{token}.ics").status_code == 404


def test_a_stale_rotate_confirm_without_a_link_creates_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    body = _tap(client, "c1:f:R")

    assert storage.calendar_feed.token_of(me.id) is None
    assert body is None or FEED_URL.search(body.get("text") or "") is None


def test_a_stale_create_shows_the_current_link(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    """Review fix: an old "Create my link" button never rotates a subscribed link."""
    me = _me(client, storage)
    _tap(client, "c1:f:n")
    token = storage.calendar_feed.token_of(me.id)

    body = _tap(client, "c1:f:n")

    assert storage.calendar_feed.token_of(me.id) == token
    assert _token(_link_message(body, outbound)) == token


def test_the_link_screen_has_no_preview(client: TestClient, storage: InMemoryStorage) -> None:
    """Review fix: Telegram's preview crawler would fetch the secret link (and stamp "last
    checked")."""
    _me(client, storage)

    body = _tap(client, "c1:f:n")

    assert body["link_preview_options"]["is_disabled"] is True
    assert client.get("/api/v1/health").status_code == 200


def test_a_stale_off_confirm_is_harmless(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _tap(client, "c1:f:n")
    _tap(client, "c1:f:X")

    _tap(client, "c1:f:X")
    _tap(client, "c1:f:n")
    again = storage.calendar_feed.token_of(me.id)
    _tap(client, "c1:f:X")  # an old message's button: acts on the current link

    assert again is not None
    assert storage.calendar_feed.token_of(me.id) is None


# Data, answers, forged taps


def test_a_tap_is_answered_and_edits_in_place(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    _me(client, storage)
    outbound.clear()

    body = _tap(client, "c1:f:s")

    assert body["method"] == "editMessageText"
    assert [s.name for s in outbound] == ["answerCallbackQuery"]


def test_every_datum_is_short(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _join(storage, me)

    bodies = [_tap(client, "c1:f:s"), _tap(client, "c1:f:n"), _tap(client, "c1:f:s")]
    bodies += [_tap(client, "c1:f:r"), _tap(client, "c1:f:x")]

    datas = [d for body in bodies for d in _datas(body)]
    assert {"c1:f:n", "c1:f:r", "c1:f:x", "c1:f:R", "c1:f:X"} <= set(datas)
    assert all(len(d.encode()) <= 12 for d in datas if d.startswith("c1:f:")), datas


@pytest.mark.parametrize("data", ["c1:f:z", "c1:f:", "c1:f:ss", "c1:f:n:1", "c1:f"])
def test_forged_data_is_ignored(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent], data: str
) -> None:
    me = _me(client, storage)
    outbound.clear()

    body = _tap(client, data)

    assert body is None
    assert [s.name for s in outbound] == ["answerCallbackQuery"]
    assert storage.calendar_feed.token_of(me.id) is None


# Entry rows


def _entry(body: Any) -> list[dict[str, Any]]:
    return [b for b in _buttons(body) if b.get("callback_data") == "c1:f:s"]


def test_schedule_has_the_entry_row(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _join(storage, me)

    [button] = _entry(_command(client, "/schedule"))

    assert button["text"] == "📅 Add to calendar"


def test_moon_has_the_entry_row(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    [button] = _entry(_command(client, "/moon"))

    assert button["text"] == "📅 Add to calendar"


def test_settings_has_the_entry_row_in_russian(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage, "ru")

    [button] = _entry(_command(client, "/settings", "ru"))

    assert button["text"] == "📅 Добавить в календарь"


def test_no_entry_rows_without_a_public_url(
    storage: InMemoryStorage, outbound: list[Sent], monkeypatch: pytest.MonkeyPatch
) -> None:
    with _app(storage, monkeypatch, "") as client:
        me = _me(client, storage)
        _join(storage, me)
        bodies = [_command(client, c) for c in ("/schedule", "/moon", "/settings")]

    for body in bodies:
        assert _entry(body) == []


def test_staff_of_a_shala_see_the_same_screen(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    anna = person(storage, "1001", "Anna")
    shala = storage.shalas.add_shala(anna.id, name="Ashtanga Almaty").id
    storage.shalas.add_staff(shala, me.id, ShalaRole.TEACHER)

    body = _tap(client, "c1:f:s")

    assert _datas(body) == ["c1:f:n"]
    assert _t("feed-moon-only") not in _flat(body["text"])
