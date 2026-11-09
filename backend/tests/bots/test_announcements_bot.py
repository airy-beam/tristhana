# ruff: noqa: RUF001
"""Announcements in the bot (NT-03 spec §2, §5, §8): the pushed message in EN and RU (plain,
no preview, `disable_notification` exactly when silent), mute and unmute editing only the
buttons with a toast, the feed screen with pins, paging and back, the shala card's pin line,
`[📣 Announcements]` and `[📣 Announce]` by policy, forged or ended sources back to
`/teachers`, every `b1:` datum within 64 bytes, and no text in any log."""

import asyncio
import itertools
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.announcement_fakes import Member, Person
from tests.bots.test_moon_bot import _notifier  # pyright: ignore[reportPrivateUsage]
from tests.fakes import FixedClock, InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.application.ports.announcements import NewAnnouncement
from tristhana.application.ports.notifications import Announcement, DeliveryStatus, Recipient
from tristhana.bots.telegram import announcements_callbacks as cb
from tristhana.domain.accounts import Account
from tristhana.domain.announcements import Source, SourceKind
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
APP = "https://tristhana.web.app"
ME_TG = 42
NOW = datetime(2026, 11, 9, 5, 0, tzinfo=UTC)
_ids = itertools.count(170_000)
T = FluentTranslator()


@dataclass
class Sent:
    name: str
    fields: dict[str, Any]


# --- the pushed message ------------------------------------------------------------------


def _ann(silent: bool, source: Source | None = None, author: str | None = "Anna") -> Announcement:
    return Announcement(
        uuid4(),
        source or Source(SourceKind.TEACHER, uuid4()),
        "Anna",
        author,
        "<b>No Mysore</b> Mon 10 Nov\nhttps://example.org",
        silent,
        date(2026, 11, 9),
    )


@pytest.mark.parametrize("silent", [True, False])
async def test_the_message_is_plain_with_no_preview(
    monkeypatch: pytest.MonkeyPatch, silent: bool
) -> None:
    notifier, sent = _notifier(monkeypatch, None)
    result = await notifier.deliver(Recipient("42", "en"), _ann(silent))
    assert result.status is DeliveryStatus.SENT
    [method] = sent
    assert isinstance(method, SendMessage)
    assert method.text == "📣 Anna · your teacher\n<b>No Mysore</b> Mon 10 Nov\nhttps://example.org"
    assert method.parse_mode is None
    preview = method.link_preview_options
    assert isinstance(preview, LinkPreviewOptions)
    assert preview.is_disabled is True
    assert method.disable_notification is silent
    markup = method.reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert [b.text for b in buttons] == [T.t("en", "ann-mute"), T.t("en", "ann-list")]
    assert all(len((b.callback_data or "").encode()) <= 64 for b in buttons)


async def test_the_shala_heads_in_russian(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier, sent = _notifier(monkeypatch, None)
    shala = Source(SourceKind.SHALA, uuid4())
    n = Announcement(uuid4(), shala, "Ashtanga Almaty", "Анна", "Текст", False, date(2026, 11, 9))
    await notifier.deliver(Recipient("42", "ru"), n)
    n2 = Announcement(uuid4(), shala, "Ashtanga Almaty", None, "Текст", False, date(2026, 11, 9))
    await notifier.deliver(Recipient("42", "ru"), n2)
    assert sent[0].text == "📣 Ashtanga Almaty · Анна\nТекст"
    assert sent[1].text == "📣 Ashtanga Almaty\nТекст"
    assert sent[0].reply_markup.inline_keyboard[0][0].text == "🔕 Не присылать"


async def test_the_text_never_reaches_a_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import GetMe

    notifier, _ = _notifier(monkeypatch, TelegramBadRequest(method=GetMe(), message="too long"))
    with caplog.at_level(logging.DEBUG):
        await notifier.deliver(Recipient("42", "en"), _ann(False))
    assert "No Mysore" not in caplog.text


# --- callback data -----------------------------------------------------------------------


def test_callbacks_round_trip_and_fit() -> None:
    for kind in SourceKind:
        source = Source(kind, uuid4())
        for data in (
            cb.feed(source, 99),
            cb.mute(source, True, "n"),
            cb.mute(source, False, "l"),
        ):
            assert len(data.encode()) <= 32
            assert cb.decode(data) is not None
        assert cb.decode(cb.feed(source, 3)) == cb.List(source, 3)
        assert cb.decode(cb.mute(source, True, "l")) == cb.Mute(source, True, "l")


@pytest.mark.parametrize(
    "data",
    ["b1:l:t:x:0", "b1:l:z:AAAAAAAAAAAAAAAAAAAAAA:0", "b1:l:t:AAAAAAAAAAAAAAAAAAAAAA:100",
     "b1:m:t:AAAAAAAAAAAAAAAAAAAAAA:q", "b2:l:t:AAAAAAAAAAAAAAAAAAAAAA:0", "", "b1"],
)  # fmt: skip
def test_malformed_callbacks(data: str) -> None:
    assert cb.decode(data) is None


# --- through the webhook ------------------------------------------------------------------


@pytest.fixture
def storage() -> InMemoryStorage:
    storage = shala_storage()
    storage.announcements.clock = FixedClock(NOW)
    return storage


@pytest.fixture
def outbound(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> list[Sent]:
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        sent.append(Sent(method.__api_method__, method.model_dump()))
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


@pytest.fixture
def client(storage: InMemoryStorage, outbound: list[Sent]) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url=APP,
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(settings, storage)) as c:
        yield c


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str = "en") -> dict[str, Any]:
    return {"id": ME_TG, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _start(client: TestClient, storage: InMemoryStorage) -> Account:
    message = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": ME_TG, "type": "private"},
        "from": _user(),
        "text": "/start",
        "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
    }
    _post(client, {"update_id": next(_ids), "message": message})
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    storage.announcements.people.setdefault(me.id, Person("Ash"))
    return me


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
    return [b for row in body.get("reply_markup", {}).get("inline_keyboard", []) for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _shala_with_me(
    storage: InMemoryStorage, me: Account, *, staff: ShalaRole | None = None
) -> UUID:
    """The same shala in both fakes: the shala port's and the announcement port's."""
    anna = person(storage, "1001", "Anna")
    shala = storage.shalas.add_shala(anna.id, name="Ashtanga Almaty").id
    repo = storage.announcements
    repo.people.setdefault(anna.id, Person("Anna"))
    repo.shala_names[shala] = "Ashtanga Almaty"
    repo.members[(shala, anna.id)] = Member(NOW - timedelta(days=60), owner=True)
    if staff is None:
        storage.shalas.add_student(shala, me.id)
        repo.members[(shala, me.id)] = Member(NOW - timedelta(days=30), student=True)
    else:
        storage.shalas.add_staff(shala, me.id, staff)
        repo.members[(shala, me.id)] = Member(NOW - timedelta(days=30), roles=frozenset({staff}))
    return shala


def _announce(storage: InMemoryStorage, author: UUID, shala: UUID, text: str, pin: bool) -> UUID:
    repo = storage.announcements
    posted = asyncio.run(
        repo.create(
            NewAnnouncement(
                author,
                Source(SourceKind.SHALA, shala),
                text,
                NOW + timedelta(days=7) if pin else None,
                NOW - timedelta(days=1),
                99,
            )
        )
    )
    assert posted.item is not None
    return posted.item.id


def test_the_feed_screen(client: TestClient, storage: InMemoryStorage) -> None:
    me = _start(client, storage)
    shala = _shala_with_me(storage, me)
    owner = next(a for (_, a), m in storage.announcements.members.items() if m.owner)
    _announce(storage, owner, shala, "Closed 1-20 August", pin=True)
    storage.announcements.clock.instant = NOW + timedelta(hours=1)
    _announce(storage, owner, shala, "Led class Sun 15 Nov, 7:00", pin=False)
    body = _tap(client, cb.feed(Source(SourceKind.SHALA, shala)))
    text = body["text"]
    assert text.startswith(T.t("en", "ann-list-title", source="Ashtanga Almaty"))
    assert text.index("Closed 1-20 August") < text.index("Led class Sun 15 Nov")
    assert "📌" in text
    assert "📅 Mon, Nov 9 · Anna" in text
    assert body["link_preview_options"]["is_disabled"] is True
    texts = _texts(body)
    assert texts[0] == T.t("en", "ann-mute")
    assert texts[-1] == T.t("en", "log-back")
    assert all(len(b["callback_data"].encode()) <= 64 for b in _buttons(body))


def test_paging(client: TestClient, storage: InMemoryStorage) -> None:
    me = _start(client, storage)
    shala = _shala_with_me(storage, me)
    owner = next(a for (_, a), m in storage.announcements.members.items() if m.owner)
    for i in range(7):
        storage.announcements.clock.instant = NOW + timedelta(minutes=i)
        _announce(storage, owner, shala, f"note {i}", pin=False)
    source = Source(SourceKind.SHALA, shala)
    first = _tap(client, cb.feed(source, 0))
    assert "note 6" in first["text"]
    assert "note 1" not in first["text"]
    assert T.t("en", "page-next") in _texts(first)
    second = _tap(client, cb.feed(source, 1))
    assert "note 1" in second["text"]
    assert T.t("en", "page-prev") in _texts(second)


def test_mute_on_the_message_edits_only_the_buttons(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _start(client, storage)
    shala = _shala_with_me(storage, me)
    source = Source(SourceKind.SHALA, shala)
    body = _tap(client, cb.mute(source, True, "n"))
    assert body["method"] == "editMessageReplyMarkup"
    assert _texts(body) == [T.t("en", "ann-unmute"), T.t("en", "ann-list")]
    assert storage.announcements.members[(shala, me.id)].muted
    [toast] = [s for s in outbound if s.name == "answerCallbackQuery"]
    assert toast.fields["text"] == T.t("en", "ann-muted")
    again = _tap(client, cb.mute(source, False, "n"))
    assert _texts(again)[0] == T.t("en", "ann-mute")
    assert not storage.announcements.members[(shala, me.id)].muted


def test_mute_on_the_feed_re_renders_it(client: TestClient, storage: InMemoryStorage) -> None:
    me = _start(client, storage)
    shala = _shala_with_me(storage, me)
    body = _tap(client, cb.mute(Source(SourceKind.SHALA, shala), True, "l"))
    assert body["method"] == "editMessageText"
    assert _texts(body)[0] == T.t("en", "ann-unmute")


def test_a_forged_or_ended_source_goes_back_to_teachers(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _start(client, storage)
    title = T.t("en", "links-title")
    feed = _tap(client, cb.feed(Source(SourceKind.TEACHER, uuid4())))
    assert title in feed["text"]
    mute = _tap(client, cb.mute(Source(SourceKind.SHALA, uuid4()), True, "n"))
    assert title in mute["text"]


def test_the_shala_card_shows_the_pin_and_the_buttons(
    client: TestClient, storage: InMemoryStorage
) -> None:
    from tristhana.bots.telegram import shalas_callbacks

    me = _start(client, storage)
    shala = _shala_with_me(storage, me)
    owner = next(a for (_, a), m in storage.announcements.members.items() if m.owner)
    _announce(storage, owner, shala, "Closed 1-20 August", pin=True)
    body = _tap(client, shalas_callbacks.on_shala("c", shala))
    assert "📌 Closed 1-20 August" in body["text"]
    texts = _texts(body)
    assert T.t("en", "ann-list") in texts
    assert T.t("en", "ann-announce") not in texts  # a student can't announce


@pytest.mark.parametrize(
    ("role", "announce"), [(ShalaRole.OFFICE, True), (ShalaRole.ASSISTANT, False)]
)
def test_announce_by_policy(
    client: TestClient, storage: InMemoryStorage, role: ShalaRole, announce: bool
) -> None:
    from tristhana.bots.telegram import shalas_callbacks

    me = _start(client, storage)
    shala = _shala_with_me(storage, me, staff=role)
    body = _tap(client, shalas_callbacks.on_shala("c", shala))
    found = [b for b in _buttons(body) if b["text"] == T.t("en", "ann-announce")]
    assert bool(found) is announce
    if found:
        assert found[0]["web_app"]["url"] == f"{APP}?open=announce&shala={shala}"


def test_long_items_are_never_cut_and_the_pin_card_has_no_preview(
    client: TestClient, storage: InMemoryStorage
) -> None:
    from tristhana.bots.telegram import shalas_callbacks

    me = _start(client, storage)
    shala = _shala_with_me(storage, me)
    owner = next(a for (_, a), m in storage.announcements.members.items() if m.owner)
    texts = [f"{i}" + "x" * 998 + "!" for i in range(3)]
    for i, text in enumerate(texts):
        storage.announcements.clock.instant = NOW + timedelta(minutes=i)
        _announce(storage, owner, shala, text, pin=i == 0)
    body = _tap(client, cb.feed(Source(SourceKind.SHALA, shala)))
    assert len(body["text"]) <= 4096
    assert all(t in body["text"] for t in texts)
    card = _tap(client, shalas_callbacks.on_shala("c", shala))
    assert card["link_preview_options"]["is_disabled"] is True
