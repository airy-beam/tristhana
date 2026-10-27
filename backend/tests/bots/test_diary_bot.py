"""Diary notes through the real webhook (PR-07, spec §5, ADR-0025): the preview and the
[📓 Note] button on the day picker (also after a status change that deleted the check-in),
the button on K, the note screen N, the confirm step before removing, the ForceReply prompt
with its visible `📓 YYYY-MM-DD` token, replies (only to our own bot's prompt, always the
sender's own account, text only, never echoed), no note on the week picker or V, round trips,
and the `n1:` codec.

The clock is fixed (Tue Oct 27, 11:00 in Almaty) by replacing the app's `SystemClock`.
`diary_callbacks` and the domain types are imported inside the tests (test-first)."""

import itertools
import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FixedClock, InMemoryCheckIns, InMemoryDays, InMemoryDiary, InMemoryStorage
from tristhana.domain.accounts import IdentityKey, IdentityProvider
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.notifications import DEFAULTS
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT_ID = 123456  # from the token
ZONE = "Asia/Almaty"
NOW = datetime(2026, 10, 27, 6, 0, tzinfo=UTC)  # Tue Oct 27, 11:00 in Almaty
TODAY = date(2026, 10, 27)
YESTERDAY = date(2026, 10, 26)
SAT = date(2026, 10, 24)
NOTE = "Felt light today. Teacher said: soft gaze in Marichyasana C."
LABEL = "Today, Tue, Oct 27"
EMPTY = (
    "No note for this day. Write anything you'd like to keep: how the practice felt, what "
    "your teacher said, a new asana, or just a thought."
)
UNREADABLE = "This note can't be read right now. You can write a new one or remove it."
PROMPT = "Write your note for today as a reply to this message. It's private, just for you."
REPLACE = "It will replace the current note. Copy the note above to edit it."
SAVED = "📓 Saved to your diary."
REMOVED = "Removed from your diary. Earlier messages in this chat stay until you delete them."
TEXT_ONLY = "Notes are text for now. Type your note as a reply to the prompt above."
TOO_LONG = re.compile(
    r"That's a bit long for one note: up to 2[, ]?000 characters\. Your text is still "  # noqa: RUF001
    r"above, so you can shorten it and resend\."
)
FALLBACK = "I can't answer messages yet. Try /start or /help 🙏"
EXPLAIN = "⚡ Energy: 1 low → 5 high · 🔥 Effort: 1 easy → 5 hard. Tap what fits, all optional."
BACK = "‹ Back"  # noqa: RUF001
STATUS_EMOJI = ["🧘", "😌", "🌙", "🌸", "🤒", "✈️", "🌱", "✓"]
_ids = itertools.count(170_000)
_OUTBOUND: list[Any] = []  # the `outbound` fixture's list, emptied before every update


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Bot API calls made directly (not as the webhook reply), as aiogram method objects."""
    sent = _OUTBOUND
    sent.clear()

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FixedClock:
    fixed = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: fixed)
    return fixed


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def client(
    storage: InMemoryStorage, clock: FixedClock, outbound: list[Any]
) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
    )
    with TestClient(create_app(settings, storage)) as c:
        yield c


# Updates


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    _OUTBOUND.clear()  # `outbound` then holds this update's direct calls only
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str = "en", user_id: int = 42) -> dict[str, Any]:
    return {"id": user_id, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _command(client: TestClient, text: str, lang: str = "en", user_id: int = 42) -> Any:
    message = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": user_id, "type": "private"},
        "from": _user(lang, user_id),
        "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text)}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str, lang: str = "en") -> Any:
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": 42, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang),
        "chat_instance": "ci",
        "data": data,
        "message": message | {"text": "…"},
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _prompt_message(
    day: date | str, from_id: int = BOT_ID, is_bot: bool = True, body: str = PROMPT
) -> dict[str, Any]:
    """A message in the chat that a reply can point at (by default: our bot's prompt)."""
    token = day if isinstance(day, str) else f"📓 {day.isoformat()}\n"
    return {
        "message_id": 30,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": from_id, "is_bot": is_bot, "first_name": "Tristhana"},
        "text": f"{token}{body}",
    }


def _message(
    client: TestClient,
    text: str | None = None,
    reply_to: dict[str, Any] | None = None,
    lang: str = "en",
    user_id: int = 42,
    chat: dict[str, Any] | None = None,
    **extra: Any,
) -> Any:
    message: dict[str, Any] = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": chat or {"id": user_id, "type": "private"},
        "from": _user(lang, user_id),
        **extra,
    }
    if text is not None:
        message["text"] = text
    if reply_to is not None:
        message["reply_to_message"] = reply_to | {"chat": message["chat"]}
    return _post(client, {"update_id": next(_ids), "message": message})


def _reply(client: TestClient, text: str, day: date = TODAY, **kw: Any) -> Any:
    return _message(client, text, _prompt_message(day), **kw)


# Reading what the bot sent


def _sent(body: Any, outbound: list[Any]) -> list[dict[str, Any]]:
    """Every message the bot sent or edited for one update: direct calls, then the reply."""
    out = [
        {"method": m.__api_method__, **m.model_dump(mode="json", exclude_none=True)}
        for m in outbound
        if m.__api_method__ in ("sendMessage", "editMessageText")
    ]
    if body and body.get("method") in ("sendMessage", "editMessageText"):
        out.append(body)
    return out


def _one(body: Any, outbound: list[Any]) -> dict[str, Any]:
    [message] = _sent(body, outbound)
    return message


def _buttons(body: Any) -> list[dict[str, Any]]:
    markup: dict[str, Any] = body.get("reply_markup") or {}
    rows: list[list[dict[str, Any]]] = markup.get("inline_keyboard", [])
    return [b for row in rows for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _data_of(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if b["text"] == text)


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


# Accounts and stored data


def _me(
    client: TestClient, storage: InMemoryStorage, zone: str | None = ZONE, lang: str = "en"
) -> Any:
    """Create the account (via /settings) and give it a zone; V's one-time reminder offer
    is answered already."""
    _command(client, "/settings", lang)
    account_id = storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, "42")]
    account = replace(storage.repo.accounts[account_id], timezone=zone)
    storage.repo.accounts[account.id] = account
    chosen = replace(DEFAULTS, practice=replace(DEFAULTS.practice, on=False))
    storage.notifications.stored[account.id] = chosen
    return account


def _note(text: str | None) -> Any:
    from tristhana.domain.diary import DiaryNote

    return DiaryNote(text)


def _with_note(storage: InMemoryStorage, me: Any, day: date, text: str | None = NOTE) -> None:
    storage.day_repo.diary_rows[(me.id, day)] = _note(text)


def _logged(storage: InMemoryStorage, me: Any, day: date, status: DayStatus) -> None:
    storage.day_repo.rows[(me.id, day)] = (DayLog(day, status), ZONE)


def _stored(storage: InMemoryStorage, me: Any, day: date) -> Any:
    return storage.day_repo.diary_rows.get((me.id, day))


class _Calls:
    """Top-level calls into the fakes (inner calls of the fake don't count)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, days: InMemoryDays) -> None:
        self.reads: list[str] = []
        self.writes: list[str] = []
        depth = [0]
        for name in ("list_range", "range_with_moon", "history"):
            self._wrap(monkeypatch, days, name, self.reads, depth)
        for name in ("upsert", "insert_if_absent", "delete"):
            self._wrap(monkeypatch, days, name, self.writes, depth, prefix="days.")
        self._wrap(monkeypatch, InMemoryDiary, "get", self.reads, depth, prefix="diary.")
        for name in ("save", "delete"):
            self._wrap(monkeypatch, InMemoryDiary, name, self.writes, depth, prefix="diary.")
        for name in ("save", "set_tag", "delete"):
            self._wrap(monkeypatch, InMemoryCheckIns, name, self.writes, depth, prefix="k.")

    @staticmethod
    def _wrap(
        monkeypatch: pytest.MonkeyPatch,
        owner: Any,
        name: str,
        into: list[str],
        depth: list[int],
        prefix: str = "",
    ) -> None:
        original: Callable[..., Any] = getattr(owner, name)

        async def counted(*args: Any, **kwargs: Any) -> Any:
            if depth[0] == 0:
                into.append(prefix + name)
            depth[0] += 1
            try:
                return await original(*args, **kwargs)
            finally:
                depth[0] -= 1

        monkeypatch.setattr(owner, name, counted)

    def clear(self) -> None:
        self.reads.clear()
        self.writes.clear()


# Entry: the day picker


def test_the_day_picker_shows_a_preview_and_the_note_button(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY)

    body = _one(_tap(client, f"d1:o:{_ymd(TODAY)}"), outbound)

    assert f"📓 {NOTE}" in body["text"]
    assert _data_of(body, "📓 Note") == f"n1:o:{_ymd(TODAY)}:d"


def test_the_preview_is_the_first_100_characters(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    long = "".join(f"{i % 10}" for i in range(99)) + "Ж" + "tail of the note" * 5
    _with_note(storage, me, YESTERDAY, long)

    body = _one(_tap(client, f"d1:o:{_ymd(YESTERDAY)}"), outbound)

    assert f"📓 {long[:100]}…" in body["text"]
    assert "tail of the note" not in body["text"]


def test_without_a_note_only_the_quiet_button(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)

    body = _one(_tap(client, f"d1:o:{_ymd(TODAY)}"), outbound)

    assert "📓" not in body["text"]
    assert _data_of(body, "📓 Note") == f"n1:o:{_ymd(TODAY)}:d"


@pytest.mark.parametrize("status", list(DayStatus))
def test_the_note_button_is_on_every_day(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any], status: DayStatus
) -> None:
    me = _me(client, storage)
    _logged(storage, me, SAT, status)
    _with_note(storage, me, SAT)

    body = _one(_tap(client, f"d1:o:{_ymd(SAT)}"), outbound)

    assert f"📓 {NOTE}" in body["text"]
    assert "📓 Note" in _texts(body)


def test_an_unreadable_note_shows_no_preview_text_but_the_button(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY, None)

    body = _one(_tap(client, f"d1:o:{_ymd(TODAY)}"), outbound)

    assert "None" not in body["text"]
    assert "📓 Note" in _texts(body)


def test_the_picker_needs_no_new_statement(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY)
    calls = _Calls(monkeypatch, storage.day_repo)

    body = _one(_tap(client, f"d1:o:{_ymd(TODAY)}"), outbound)

    assert f"📓 {NOTE}" in body["text"]
    assert calls.reads == ["range_with_moon"]  # the notes come along, no diary read
    assert calls.writes == []


def test_the_preview_stays_after_a_status_change_that_deleted_the_check_in(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    from tristhana.domain.check_in import CheckIn

    me = _me(client, storage)
    d = _ymd(TODAY)
    _logged(storage, me, TODAY, DayStatus.PRACTICED)
    storage.day_repo.check_in_rows[(me.id, TODAY)] = CheckIn(mood=4)
    _with_note(storage, me, TODAY)

    _tap(client, f"d1:s:{d}:r")
    body = _one(_tap(client, f"d1:o:{d}"), outbound)

    assert storage.day_repo.check_in_rows == {}
    assert _stored(storage, me, TODAY) == _note(NOTE)
    assert f"📓 {NOTE}" in body["text"]
    assert "📓 Note" in _texts(body)


def test_clearing_the_day_keeps_the_note(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _logged(storage, me, TODAY, DayStatus.SICK)
    _with_note(storage, me, TODAY)

    body = _one(_tap(client, f"d1:x:{_ymd(TODAY)}"), outbound)

    assert _stored(storage, me, TODAY) == _note(NOTE)
    assert f"📓 {NOTE}" in body["text"]


# Entry: the check-in screen K


def test_k_has_the_note_button_and_no_preview(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = _me(client, storage)
    _logged(storage, me, TODAY, DayStatus.PRACTICED)
    _with_note(storage, me, TODAY)
    calls = _Calls(monkeypatch, storage.day_repo)

    body = _one(_tap(client, f"k1:o:{_ymd(TODAY)}"), outbound)

    assert EXPLAIN in body["text"]
    assert _data_of(body, "📓 Note") == f"n1:o:{_ymd(TODAY)}:k"
    assert NOTE not in body["text"]
    assert len(calls.reads) == 1  # K stays one statement
    assert not any(r.startswith("diary.") for r in calls.reads)


# Never on the week picker, V or P's summary


def test_no_note_text_or_marker_on_the_week_picker(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    for back in range(7):
        _with_note(storage, me, TODAY - timedelta(days=back), f"note {back}")
    _logged(storage, me, YESTERDAY, DayStatus.PRACTICED)

    body = _one(_tap(client, f"d1:w:{_ymd(TODAY)}"), outbound)

    shown = body["text"] + " ".join(_texts(body))
    assert "📓" not in shown
    assert "note " not in shown


def test_no_note_on_the_done_screen(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _logged(storage, me, TODAY, DayStatus.PRACTICED)
    _with_note(storage, me, TODAY)

    body = _one(_tap(client, f"p1:v:{_ymd(TODAY)}"), outbound)

    shown = body["text"] + " ".join(_texts(body))
    assert "📓" not in shown
    assert NOTE not in shown


# Screen N


def test_n_shows_the_date_the_note_and_its_actions(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY)
    d = _ymd(TODAY)
    calls = _Calls(monkeypatch, storage.day_repo)

    body = _one(_tap(client, f"n1:o:{d}:d"), outbound)

    assert LABEL in body["text"].split("\n")[0]
    assert NOTE in body["text"]
    assert _data_of(body, "✏️ Rewrite") == f"n1:r:{d}:d"
    assert _data_of(body, "Remove note") == f"n1:y:{d}:d"
    assert _data_of(body, BACK) == f"n1:b:{d}:d"
    assert "✏️ Write" not in _texts(body)
    assert calls.reads == ["diary.get"]  # + 1 PK read, nothing else
    assert calls.writes == []


def test_n_edits_in_place_after_answering_first(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)

    reply = _tap(client, f"n1:o:{_ymd(TODAY)}:d")

    assert [m.__api_method__ for m in outbound][:1] == ["answerCallbackQuery"]
    assert _one(reply, outbound)["method"] == "editMessageText"


def test_n_without_a_note_offers_writing_with_gentle_examples(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)
    d = _ymd(YESTERDAY)

    body = _one(_tap(client, f"n1:o:{d}:d"), outbound)

    assert body["text"].split("\n")[0].endswith("Yesterday, Mon, Oct 26")
    assert EMPTY in " ".join(body["text"].split())
    assert _data_of(body, "✏️ Write") == f"n1:w:{d}:d"
    assert "Remove note" not in _texts(body)
    assert "✏️ Rewrite" not in _texts(body)
    assert BACK in _texts(body)


def test_n_with_an_unreadable_note_offers_writing_and_removing(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY, None)
    d = _ymd(TODAY)

    body = _one(_tap(client, f"n1:o:{d}:d"), outbound)

    assert UNREADABLE in body["text"]
    assert _data_of(body, "Remove note") == f"n1:y:{d}:d"
    assert {"✏️ Write", "✏️ Rewrite"} & set(_texts(body))


@pytest.mark.parametrize("status", list(DayStatus))
def test_n_never_shows_the_status(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any], status: DayStatus
) -> None:
    me = _me(client, storage)
    _logged(storage, me, TODAY, status)
    _with_note(storage, me, TODAY, "plain words")

    body = _one(_tap(client, f"n1:o:{_ymd(TODAY)}:d"), outbound)

    assert all(e not in body["text"] for e in STATUS_EMOJI), body["text"]
    assert "Ladies" not in body["text"]


def test_n_sends_the_note_as_plain_text(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    markup = "<b>not bold</b> *nor this* [x](http://e.x) `code`"
    _with_note(storage, me, TODAY, markup)

    body = _one(_tap(client, f"n1:o:{_ymd(TODAY)}:d"), outbound)

    assert markup in body["text"]
    assert body.get("parse_mode") is None
    assert "entities" not in body


def test_n_in_russian(client: TestClient, storage: InMemoryStorage, outbound: list[Any]) -> None:
    _me(client, storage, lang="ru")

    body = _one(_tap(client, f"n1:o:{_ymd(TODAY)}:d", lang="ru"), outbound)

    assert "Сегодня, вт, 27 окт." in body["text"].split("\n")[0]
    assert (
        "Заметки за этот день нет. Можно записать что угодно: как прошла практика, что сказал "
        "преподаватель, новая асана или просто мысль."
    ) in " ".join(body["text"].split())
    assert "✏️ Написать" in _texts(body)


def test_back_from_n_returns_to_the_day_picker(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY)

    body = _one(_tap(client, f"n1:b:{_ymd(TODAY)}:d"), outbound)

    assert body["text"].startswith(LABEL)
    assert "🧘 Practiced" in _texts(body)
    assert "📓 Note" in _texts(body)


def test_back_from_n_opened_on_k_returns_to_k(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _logged(storage, me, TODAY, DayStatus.PRACTICED)
    d = _ymd(TODAY)

    opened = _one(_tap(client, f"n1:o:{d}:k"), outbound)
    back = _one(_tap(client, f"n1:b:{d}:k"), outbound)

    assert _data_of(opened, BACK) == f"n1:b:{d}:k"
    assert _data_of(opened, "✏️ Write") == f"n1:w:{d}:k"
    assert EXPLAIN in back["text"]


# Removing: confirm first


def test_remove_asks_first_with_no_statement(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY)
    d = _ymd(TODAY)
    calls = _Calls(monkeypatch, storage.day_repo)

    body = _one(_tap(client, f"n1:y:{d}:d"), outbound)

    assert "Remove this note?" in body["text"]
    assert _data_of(body, "Remove") == f"n1:x:{d}:d"
    assert _data_of(body, BACK) == f"n1:o:{d}:d"
    assert (calls.reads, calls.writes) == ([], [])
    assert _stored(storage, me, TODAY) == _note(NOTE)


def test_confirmed_remove_deletes_and_says_so_honestly(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = _me(client, storage)
    _logged(storage, me, TODAY, DayStatus.PRACTICED)
    _with_note(storage, me, TODAY)
    d = _ymd(TODAY)
    calls = _Calls(monkeypatch, storage.day_repo)

    body = _one(_tap(client, f"n1:x:{d}:d"), outbound)

    assert _stored(storage, me, TODAY) is None
    assert storage.day_repo.rows[(me.id, TODAY)][0].status is DayStatus.PRACTICED
    assert REMOVED in " ".join(body["text"].split())
    assert NOTE not in body["text"]
    assert "✏️ Write" in _texts(body)
    assert "Remove note" not in _texts(body)
    assert calls.writes == ["diary.delete"]  # 1 delete, no read
    assert calls.reads == []


def test_remove_twice_is_harmless(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)

    body = _one(_tap(client, f"n1:x:{_ymd(TODAY)}:d"), outbound)

    assert REMOVED in " ".join(body["text"].split())


# Writing: the ForceReply prompt


def test_write_sends_a_new_prompt_with_the_token_and_force_reply(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _me(client, storage)
    calls = _Calls(monkeypatch, storage.day_repo)

    reply = _tap(client, f"n1:w:{_ymd(TODAY)}:d")
    body = _one(reply, outbound)

    assert [m.__api_method__ for m in outbound][:1] == ["answerCallbackQuery"]
    assert body["method"] == "sendMessage"  # ForceReply can't go on an edit
    assert body["text"].startswith("📓 2026-10-27\n")
    assert PROMPT in " ".join(body["text"].split())
    assert REPLACE not in body["text"]
    assert body["reply_markup"]["force_reply"] is True
    assert body["reply_markup"]["input_field_placeholder"] == "Your note…"
    assert body.get("parse_mode") is None
    assert (calls.reads, calls.writes) == ([], [])  # 0 statements


def test_rewrite_adds_the_replace_line_with_no_read(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY)
    opened = _one(_tap(client, f"n1:o:{_ymd(TODAY)}:d"), outbound)
    calls = _Calls(monkeypatch, storage.day_repo)

    body = _one(_tap(client, _data_of(opened, "✏️ Rewrite")), outbound)

    assert body["text"].startswith("📓 2026-10-27\n")
    assert REPLACE in " ".join(body["text"].split())
    assert (calls.reads, calls.writes) == ([], [])  # the flag rides in the button (n1:r)


@pytest.mark.parametrize(
    ("day", "lang", "line"),
    [
        (YESTERDAY, "en", "Write your note for yesterday as a reply to this message."),
        (SAT, "en", "Write your note for Sat, Oct 24 as a reply to this message."),
        (TODAY, "ru", "Напиши заметку за сегодня в ответ на это сообщение."),
        (YESTERDAY, "ru", "Напиши заметку за вчера в ответ на это сообщение."),
        (SAT, "ru", "Напиши заметку за сб, 24 окт. в ответ на это сообщение."),  # noqa: RUF001
    ],
)
def test_the_prompt_names_the_day_and_the_token_stays_iso(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    day: date,
    lang: str,
    line: str,
) -> None:
    _me(client, storage, lang=lang)

    body = _one(_tap(client, f"n1:w:{_ymd(day)}:d", lang=lang), outbound)

    assert body["text"].startswith(f"📓 {day.isoformat()}\n")
    assert line in " ".join(body["text"].split())


def test_the_russian_placeholder(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage, lang="ru")

    body = _one(_tap(client, f"n1:w:{_ymd(TODAY)}:d", lang="ru"), outbound)

    assert body["reply_markup"]["input_field_placeholder"] == "Твоя заметка…"


# The reply


def test_a_reply_to_our_prompt_saves_and_never_echoes_the_text(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = _me(client, storage)
    calls = _Calls(monkeypatch, storage.day_repo)

    body = _one(_reply(client, NOTE), outbound)

    assert _stored(storage, me, TODAY) == _note(NOTE)
    assert body["method"] == "sendMessage"
    assert SAVED in body["text"]
    assert NOTE not in body["text"]
    assert "Marichyasana" not in body["text"]
    assert _data_of(body, "✏️ Rewrite") == f"n1:r:{_ymd(TODAY)}:d"
    assert _data_of(body, "Remove note") == f"n1:y:{_ymd(TODAY)}:d"
    assert calls.writes == ["diary.save"]  # 1 upsert
    assert calls.reads == []


def test_a_reply_is_normalised(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    _reply(client, "  line one\r\nline two \n")

    assert _stored(storage, me, TODAY) == _note("line one\nline two")


def test_a_reply_saves_plain_text_and_ignores_entities(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    _reply(client, "bold move", entities=[{"type": "bold", "offset": 0, "length": 4}])

    assert _stored(storage, me, TODAY) == _note("bold move")


def test_a_reply_to_an_old_prompt_writes_that_prompts_day_and_replaces(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, YESTERDAY, "written since")
    _with_note(storage, me, TODAY, "today's own")

    _reply(client, "from the old prompt", day=YESTERDAY)

    assert _stored(storage, me, YESTERDAY) == _note("from the old prompt")
    assert _stored(storage, me, TODAY) == _note("today's own")


def test_a_reply_always_writes_the_senders_own_account(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    _reply(client, "someone else's words", user_id=43)

    other = storage.repo.identities[IdentityKey(IdentityProvider.TELEGRAM, "43")]
    assert _stored(storage, me, TODAY) is None
    assert storage.day_repo.diary_rows.keys() == {(other, TODAY)}


def test_a_blank_reply_removes_the_note(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY)

    _reply(client, "   \n ")

    assert _stored(storage, me, TODAY) is None


def test_too_long_is_refused_and_nothing_saved(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY, "kept")
    long = "a long story " * 200  # 2600 code points

    body = _one(_reply(client, long), outbound)

    assert _stored(storage, me, TODAY) == _note("kept")
    assert TOO_LONG.search(" ".join(body["text"].split())), body["text"]
    assert "a long story" not in body["text"]


@pytest.mark.parametrize(
    "media",
    [
        {"voice": {"file_id": "v1", "file_unique_id": "u1", "duration": 3}},
        {
            "photo": [{"file_id": "p1", "file_unique_id": "u2", "width": 1, "height": 1}],
            "caption": "a caption is not a note",
        },
        {
            "sticker": {
                "file_id": "s1",
                "file_unique_id": "u3",
                "type": "regular",
                "width": 1,
                "height": 1,
                "is_animated": False,
                "is_video": False,
            }
        },
    ],
)
def test_a_non_text_reply_gets_text_only(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any], media: dict[str, Any]
) -> None:
    _me(client, storage)

    body = _one(_message(client, None, _prompt_message(TODAY), **media), outbound)

    assert TEXT_ONLY in " ".join(body["text"].split())
    assert storage.day_repo.diary_rows == {}


@pytest.mark.parametrize(
    "target",
    [
        _prompt_message(TODAY, from_id=42, is_bot=False),  # the person's own message
        _prompt_message(TODAY, from_id=999_999, is_bot=True),  # another bot's message
        _prompt_message("", body="Today, Tue, Oct 27\n\nHow was your day?"),  # ours, no token
        _prompt_message("📓 27.10.2026\n"),  # not the token
        _prompt_message("📓 2026-10-27 "),  # the token must end the first line
        _prompt_message("x📓 2026-10-27\n"),
        _prompt_message("📓 2026-13-45\n"),  # not a date
    ],
)
def test_other_replies_get_the_fallback_and_save_nothing(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any], target: dict[str, Any]
) -> None:
    _me(client, storage)

    body = _one(_message(client, NOTE, target), outbound)

    assert body["text"] == FALLBACK
    assert storage.day_repo.diary_rows == {}


def test_a_command_sent_as_a_reply_to_the_prompt_runs_and_saves_nothing(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    # ForceReply keeps the field in reply mode: Menu → /log is then a reply to the prompt.
    me = _me(client, storage)
    _with_note(storage, me, TODAY, "kept")
    command = [{"type": "bot_command", "offset": 0, "length": 4}]

    body = _one(_message(client, "/log", _prompt_message(TODAY), entities=command), outbound)

    assert body["text"].startswith(LABEL)  # the log screen
    assert _stored(storage, me, TODAY) == _note("kept")


def test_a_command_sent_as_a_reply_to_another_bot_message_runs(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)
    command = [{"type": "bot_command", "offset": 0, "length": 4}]
    target = _prompt_message("", body="Today, Tue, Oct 27\n\nHow was your day?")

    body = _one(_message(client, "/log", target, entities=command), outbound)

    assert body["text"].startswith(LABEL)
    assert storage.day_repo.diary_rows == {}


def test_plain_text_without_a_reply_gets_the_fallback(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)

    body = _one(_message(client, NOTE), outbound)

    assert body["text"] == FALLBACK
    assert storage.day_repo.diary_rows == {}


def test_a_reply_in_a_group_is_ignored(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)

    body = _message(client, NOTE, _prompt_message(TODAY), chat={"id": -100, "type": "group"})

    assert _sent(body, outbound) == []
    assert storage.day_repo.diary_rows == {}


def test_a_reply_with_a_future_token_date_saves_nothing(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)

    body = _one(_reply(client, NOTE, day=TODAY + timedelta(days=2)), outbound)

    assert body["text"].startswith("That day hasn't come yet in your time zone.")
    assert storage.day_repo.diary_rows == {}


def test_a_reply_with_a_token_before_2000_saves_nothing(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)

    _one(_reply(client, NOTE, day=date(1999, 12, 31)), outbound)

    assert storage.day_repo.diary_rows == {}


# One instant, two dates: Kiritimati (UTC+14) is already on Tue Oct 20, Honolulu (UTC-10)
# still on Mon Oct 19.
EDGE = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("zone", "saved"), [("Pacific/Kiritimati", True), ("Pacific/Honolulu", False)]
)
def test_the_token_date_is_checked_in_the_senders_zone(
    client: TestClient, storage: InMemoryStorage, clock: FixedClock, zone: str, saved: bool
) -> None:
    me = _me(client, storage, zone=zone)
    clock.instant = EDGE

    _reply(client, NOTE, day=date(2026, 10, 20))

    assert (_stored(storage, me, date(2026, 10, 20)) is not None) is saved


def test_the_saved_message_in_russian(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage, lang="ru")

    body = _one(_reply(client, "Заметка", lang="ru"), outbound)

    assert "📓 Сохранено в дневнике." in body["text"]
    assert "Заметка" not in body["text"].replace("Удалить заметку", "")


# Failures


def test_a_database_outage_answers_gently(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _with_note(storage, me, TODAY)
    storage.day_repo.down = True

    opened = _tap(client, f"n1:o:{_ymd(TODAY)}:d")
    replied = _reply(client, NOTE)

    assert "Sorry, I've hit a small hiccup on my side." in str(opened) + str(outbound)
    assert "Sorry, I've hit a small hiccup on my side." in str(replied)


def test_a_future_date_on_n_shows_the_week(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _me(client, storage)

    body = _one(_tap(client, f"n1:o:{_ymd(TODAY + timedelta(days=3))}:d"), outbound)

    assert body["text"].startswith("That day hasn't come yet in your time zone.")


@pytest.mark.parametrize("data", ["n1:zz", "n1:o:20261399:d", "n1:o:20261027:q", "n1:o"])
def test_malformed_note_taps_are_only_answered(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any], data: str
) -> None:
    _me(client, storage)

    body = _tap(client, data)

    assert _sent(body, outbound) == []
    assert storage.day_repo.diary_rows == {}


# Codecs: every n1: callback round-trips and fits


def _all_note_callbacks(day: date) -> list[str]:
    return [f"n1:{a}:{_ymd(day)}:{origin}" for a in "owryxb" for origin in "dk"]


@pytest.mark.parametrize("day", [date(2000, 1, 1), TODAY, date(2099, 12, 31)])
def test_every_note_callback_round_trips_and_fits(day: date) -> None:
    from tristhana.bots.telegram import diary_callbacks

    for data in _all_note_callbacks(day):
        cb = diary_callbacks.decode(data)
        assert cb is not None, data
        assert diary_callbacks.encode(cb) == data
        assert len(data.encode()) <= 17  # spec §5; Telegram's limit is 64
    assert len(set(_all_note_callbacks(day))) == 12


@pytest.mark.parametrize(
    "data",
    [None, "", "n1", "n1:o", "n1:o:20261027", "n1:o:20261399:d", "n1:o:19991231:d",
     "n1:o:20261027:x", "n1:o:20261027:d:1", "n1:q:20261027:d", "n2:o:20261027:d",
     "d1:o:20261027", "n1:w:2026-10-27:d"],
)  # fmt: skip
def test_malformed_note_callbacks(data: str | None) -> None:
    from tristhana.bots.telegram import diary_callbacks

    assert diary_callbacks.decode(data) is None


def test_note_buttons_on_every_screen_fit_64_bytes(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    me = _me(client, storage)
    _logged(storage, me, TODAY, DayStatus.PRACTICED)
    _with_note(storage, me, TODAY)
    d = _ymd(TODAY)

    for data in (f"d1:o:{d}", f"k1:o:{d}", f"n1:o:{d}:d", f"n1:y:{d}:d"):
        [message] = _sent(_tap(client, data), outbound)
        assert _buttons(message)
        for b in _buttons(message):
            assert len(b.get("callback_data", "").encode()) <= 64
