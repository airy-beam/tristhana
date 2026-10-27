"""Progression screens through the real webhook (PR-08, spec §5): /asanas, G unset (with and
without a suggestion; a start never celebrates), G set (next, later, items, change), a give
that celebrates in place with Undo, a stale give, the "New asana? 🎉" question on P (Mysore
and 1:1 only, only after a length tap, "Not new" remembered, "Yes, new" celebrates on P),
"🧘 My practice" first on L, and the `g1:` codec (≤ 64 bytes, malformed ignored)."""

import itertools
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.bots.telegram.progression_callbacks import ProgressionCallback, decode, encode
from tristhana.domain.practice import Practice, PracticeContext, PracticeLength
from tristhana.domain.progression import Position
from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
_ids = itertools.count(90_000)


@pytest.fixture(autouse=True)
def outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def client(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
    )
    with TestClient(create_app(settings, storage)) as c:
        yield c


def _today() -> date:
    return datetime.now(UTC).astimezone(ZoneInfo("UTC")).date()  # en: provisional UTC


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str) -> dict[str, Any]:
    return {"id": 42, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _command(client: TestClient, text: str = "/asanas", lang: str = "en") -> Any:
    message = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user(lang),
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


def _buttons(body: Any) -> list[dict[str, str]]:
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if text in b["text"])


def _state(storage: InMemoryStorage) -> Any:
    [state] = storage.day_repo.progression_rows.values()
    return state


def _set(client: TestClient, number: int, key: str) -> Any:
    return _tap(client, f"g1:s:{number}:{key}")


# G


def test_asanas_unset_without_history(client: TestClient) -> None:
    body = _command(client)

    assert body["method"] == "sendMessage"
    assert body["text"].startswith("🧘 My asanas")
    assert "Set it once" in body["text"]
    assert _texts(body) == ["Choose…", "Sun salutations and standing"]


def test_unset_suggests_from_the_log(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")
    [account] = storage.repo.accounts.values()  # type: ignore[attr-defined]
    day = _today() - timedelta(days=1)
    _tap(client, f"d1:s:{_ymd(day)}:p")
    storage.day_repo.practice_rows[(account.id, day)] = Practice(
        context=PracticeContext.MYSORE, length=PracticeLength(("primary",), "kurmasana")
    )
    body = _tap(client, "g1:o")
    suggestion = "From your log: Primary → Kurmasana"
    assert suggestion in _texts(body)
    started = _tap(client, _data(body, suggestion))
    assert "Saved: your practice ends at Kurmasana." in started["text"]
    assert "🎉" not in started["text"].split("\n\n")[1]  # a start never celebrates
    assert _state(storage).position == Position("primary", "kurmasana")


def test_set_screen_offers_next_later_items_and_change(client: TestClient) -> None:
    body = _set(client, 1, "navasana")

    assert "Your practice: ½ Primary → Navasana" not in body["text"]
    assert "Your practice: Primary → Navasana" in body["text"]
    texts = _texts(body)
    assert texts[0] == "↩︎ Undo"
    assert "🎉 New asana: Bhujapidasana" in texts
    assert "🎉 Another new asana…" in texts
    assert {"🎉 Drop-backs", "🎉 Standing up", "🎉 Viparita Chakrasana (tic-tacs)"} <= set(texts)
    assert "✏️ Change" in texts


def test_a_give_celebrates_in_place_with_undo(client: TestClient, storage: InMemoryStorage) -> None:
    body = _set(client, 1, "navasana")
    given = _tap(client, _data(body, "New asana: Bhujapidasana"))

    assert given["method"] == "editMessageText"
    assert "🎉 New asana: Bhujapidasana. Enjoy it!" in given["text"]
    assert "Your practice: Primary → Bhujapidasana" in given["text"]
    undone = _tap(client, _data(given, "Undo"))
    assert "Undone." in undone["text"]
    assert _state(storage).position == Position("primary", "navasana")


def test_series_complete_and_next_series_begin(client: TestClient) -> None:
    _set(client, 1, "urdhva-mukha-paschimottanasana")
    full = _tap(client, "g1:g:1:setu-bandhasana")
    assert "🎉 Full Primary: Yoga Chikitsa." in full["text"]
    begins = _tap(client, "g1:g:2:pasasana")
    assert "🎉 Intermediate begins: Nadi Shodhana." in begins["text"]
    assert "Your practice: Primary + Intermediate → Pasasana" in begins["text"]


def test_russian_celebration(client: TestClient) -> None:
    _tap(client, "g1:s:1:setu-bandhasana", lang="ru")
    body = _tap(client, "g1:g:2:pasasana", lang="ru")
    assert "🎉 Вторая серия начинается: Нади Шодхана." in body["text"]


def test_a_stale_give_says_already(client: TestClient) -> None:
    _set(client, 1, "kurmasana")
    body = _tap(client, "g1:g:1:navasana")
    assert "That's already in your practice." in body["text"]


def test_given_again_after_change_back_is_quiet(client: TestClient) -> None:
    _set(client, 1, "navasana")
    _tap(client, "g1:g:1:bhujapidasana")
    _set(client, 1, "navasana")
    body = _tap(client, "g1:g:1:bhujapidasana")
    assert "Bhujapidasana is in your practice." in body["text"]
    assert "Enjoy it" not in body["text"]


def test_items_celebrate_and_toggle_in_change(client: TestClient, storage: InMemoryStorage) -> None:
    _set(client, 1, "setu-bandhasana")
    body = _tap(client, "g1:i:drop-backs:1")
    assert "🎉 Drop-backs: a lovely step." in body["text"]
    assert "Backbends: Drop-backs" in body["text"]
    change = _tap(client, "g1:c")
    assert "✓ Drop-backs" in _texts(change)
    _tap(client, _data(change, "✓ Drop-backs"))
    assert _state(storage).items == frozenset()


def test_a_late_jump_across_series_names_both_stops(client: TestClient) -> None:
    _set(client, 1, "navasana")
    body = _tap(client, "g1:g:2:krounchasana")
    assert "🎉 New asanas: Bhujapidasana → Krounchasana" in body["text"]
    assert "🎉 Full Primary: Yoga Chikitsa." in body["text"]
    assert "🎉 Intermediate begins: Nadi Shodhana." in body["text"]


def test_undoing_the_start_reads_once_more_for_the_suggestion(
    client: TestClient, storage: InMemoryStorage
) -> None:
    start = _set(client, 1, "navasana")
    body = _tap(client, _data(start, "Undo"))
    assert "Undone." in body["text"]
    assert "Set it once" in body["text"]
    assert storage.day_repo.progression_rows == {}


def test_russian_pickers_read_naturally(client: TestClient) -> None:
    _tap(client, "g1:s:1:navasana", lang="ru")
    change = _tap(client, "g1:c", lang="ru")
    assert "Вторая серия" in _texts(change)
    grid = _tap(client, _data(change, "Вторая серия"), lang="ru")
    assert grid["text"] == "Последняя асана, вторая серия:"


def test_a_change_offers_undo(client: TestClient) -> None:
    _set(client, 1, "navasana")
    body = _set(client, 1, "setu-bandhasana")
    assert _texts(body)[0] == "↩︎ Undo"


def test_change_pickers_and_later_grid(client: TestClient) -> None:
    _set(client, 1, "navasana")
    change = _tap(client, "g1:c")
    assert {"Primary", "Intermediate", "Advanced A", "Advanced B"} <= set(_texts(change))
    grid = _tap(client, _data(change, "Intermediate"))
    assert "Your last asana in Intermediate:" in grid["text"]
    later = _tap(client, "g1:p:g:0:0")
    assert later["text"] == "Which new asana?"
    assert _texts(later)[0] == "Bhujapidasana"
    assert all(b["callback_data"].startswith("g1:g:") for b in _buttons(later)[:-2])


# P and L


def _mysore_day(client: TestClient) -> str:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:m")
    return d


def test_p_asks_after_a_length_past_the_last_asana(client: TestClient) -> None:
    _set(client, 1, "navasana")
    d = _mysore_day(client)
    body = _tap(client, f"p1:l:{d}:11:kurmasana")

    assert "Kurmasana goes beyond your last asana. New asana? 🎉" in body["text"]
    assert "How do you feel after practice?" not in body["text"]  # one question at a time
    yes = _tap(client, _data(body, "Yes, new"))
    assert "🎉 New asanas: Bhujapidasana → Kurmasana" in yes["text"]
    assert "goes beyond" not in yes["text"]


def test_not_new_is_remembered_for_that_asana(client: TestClient, storage: InMemoryStorage) -> None:
    _set(client, 1, "navasana")
    d = _mysore_day(client)
    body = _tap(client, f"p1:l:{d}:11:kurmasana")
    no = _tap(client, _data(body, "Not new"))
    assert "goes beyond" not in no["text"]
    _tap(client, f"p1:l:{d}:11:navasana")
    again = _tap(client, f"p1:l:{d}:11:kurmasana")
    assert "goes beyond" not in again["text"]
    assert _state(storage).position == Position("primary", "navasana")


@pytest.mark.parametrize("context", ["l", "s"])
def test_never_asks_for_led_or_self_practice(client: TestClient, context: str) -> None:
    _set(client, 1, "navasana")
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:{context}")
    body = _tap(client, f"p1:l:{d}:11:kurmasana")
    assert "goes beyond" not in body["text"]


def test_never_asks_when_unset_or_on_reopening(client: TestClient) -> None:
    d = _mysore_day(client)
    assert "goes beyond" not in _tap(client, f"p1:l:{d}:11:kurmasana")["text"]
    _set(client, 1, "navasana")
    assert "goes beyond" not in _tap(client, f"p1:o:{d}")["text"]


def test_lengths_put_my_practice_first(client: TestClient) -> None:
    _set(client, 2, "pincha-mayurasana")
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    body = _tap(client, f"p1:m:{d}")
    texts = _texts(body)
    assert texts[:2] == [
        "🧘 My practice: Primary + Intermediate → Pincha Mayurasana",
        "🧘 My practice: Intermediate → Pincha Mayurasana",
    ]
    assert "Full Primary" in texts
    assert "🧘 My asanas" in texts


# Codec


def test_every_callback_round_trips_within_64_bytes() -> None:
    from pathlib import Path

    catalog = load_practice_catalog(Path(__file__).resolve().parents[3] / "data" / "seed").catalog
    longest = max((p.key for s in catalog.series for p in s.stops), key=len)
    day = date(2026, 10, 27)
    cases = [
        ProgressionCallback("open"),
        ProgressionCallback("change"),
        ProgressionCallback("give", 4, longest, day),
        ProgressionCallback("give", 1, "navasana"),
        ProgressionCallback("set", 0),
        ProgressionCallback("set", 2, longest),
        ProgressionCallback("not_new", 4, longest, day),
        ProgressionCallback("item", 1, "viparita-chakrasana"),
        ProgressionCallback("series", mode="s"),
        ProgressionCallback("grid", 2, mode="s", page=1),
        ProgressionCallback("grid", 0, mode="g", page=0),
        ProgressionCallback("undo", 123456789012),
    ]
    for cb in cases:
        data = encode(cb)
        assert len(data.encode()) <= 64, data
        assert decode(data) == cb


@pytest.mark.parametrize(
    "data",
    [
        "g1",
        "g1:x",
        "g1:g:7:navasana",
        "g1:g:1:",
        "g1:s:0:navasana",
        "g1:g:1:Nava sana",
        "g1:g:1:navasana:20261399",
        "g1:n:1:navasana",
        "g1:i:drop-backs:2",
        "g1:p:x:1:0",
        "g1:u:0",
        "g1:u:abc",
        "g1:u:²",
        "g1:g:²:navasana",
        "p1:o:20261027",
    ],
)
def test_malformed_callbacks_decode_to_none(data: str) -> None:
    assert decode(data) is None


def test_malformed_taps_are_ignored(client: TestClient) -> None:
    assert _tap(client, "g1:g:9:nope") is None


def test_tic_tacs_carry_their_everyday_name_in_russian(client: TestClient) -> None:
    body = _tap(client, "g1:s:1:setu-bandhasana", lang="ru")
    assert "🎉 Випарита Чакрасана (тик-токи)" in _texts(body)
