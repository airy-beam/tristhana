"""What follows 🧘 Practiced, through the real webhook (PR-02, PR-03, PR-05; UI-06 P0, P1, V):
three buttons after the save, the details screen behind "Add details", the done screen."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.bots.statements import Statements
from tests.fakes import InMemoryStorage
from tristhana.bots.telegram.practice_callbacks import PracticeCallback, Range, decode, encode
from tristhana.domain.days import DayStatus
from tristhana.domain.practice import PracticeContext
from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
_ids = itertools.count(70_000)


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


def _today(lang: str = "en") -> date:
    """The bot's "today" for a new account (no zone yet → provisional: en UTC, ru Moscow)."""
    zone = ZoneInfo("Europe/Moscow" if lang == "ru" else "UTC")
    return datetime.now(UTC).astimezone(zone).date()


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _tap(client: TestClient, data: str, lang: str = "en") -> Any:
    user = {"id": 42, "is_bot": False, "first_name": "Ash", "language_code": lang}
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": 42, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": user,
        "chat_instance": "ci",
        "data": data,
        "message": message | {"text": "…"},
    }
    response = client.post(
        "/telegram/webhook",
        json={"update_id": next(_ids), "callback_query": callback},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _buttons(body: Any) -> list[dict[str, str]]:
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _rows(body: Any) -> list[list[str]]:
    return [[b["text"] for b in row] for row in body["reply_markup"]["inline_keyboard"]]


def _main(body: Any) -> str:
    return body["text"]


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if b["text"].endswith(text))


def _practice(storage: InMemoryStorage) -> Any:
    [practice] = storage.day_repo.practice_rows.values()
    return practice


# After "Practiced" (P0)


def test_practiced_shows_two_buttons_without_a_previous_practice(client: TestClient) -> None:
    d = _ymd(_today())

    body = _tap(client, f"d1:s:{d}:p")

    assert body["text"].startswith("✓ Today, ")
    assert "Practice done 🙏" in body["text"]
    assert "Add details? Optional" not in body["text"]  # the buttons say it
    assert _rows(body) == [["📝 Add details"], ["✓ Done"]]  # nothing to copy yet
    assert [b["callback_data"] for b in _buttons(body)] == [f"p1:o:{d}", f"p1:v:{d}"]


def test_practiced_shows_three_buttons_with_a_previous_practice(client: TestClient) -> None:
    yesterday, d = _ymd(_today() - timedelta(days=1)), _ymd(_today())
    _tap(client, f"d1:s:{yesterday}:p")
    _tap(client, f"p1:t:{yesterday}:60")

    body = _tap(client, f"d1:s:{d}:p")

    assert body["text"].endswith("Last time: 60 min")
    assert _rows(body) == [["🔁 Same as last time"], ["📝 Add details"], ["✓ Done"]]
    assert _data(body, "🔁 Same as last time") == f"p1:s:{d}"


def test_practiced_in_russian(client: TestClient) -> None:
    d = _ymd(_today("ru"))

    body = _tap(client, f"d1:s:{d}:p", lang="ru")

    assert _rows(body) == [["📝 Добавить детали"], ["✓ Готово"]]


def test_practiced_costs_one_write_and_one_read(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tap(client, "w1:n")  # the account exists
    statements = Statements(monkeypatch, storage)

    _tap(client, f"d1:s:{_ymd(_today())}:p")

    assert statements.names == [
        "InMemoryDays.upsert",
        "InMemoryPractices.recent_with_progression",
    ]


def test_practiced_again_shows_the_stored_details_from_the_write_alone(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    yesterday, d = _ymd(_today() - timedelta(days=1)), _ymd(_today())
    _tap(client, f"d1:s:{yesterday}:p")
    _tap(client, f"p1:c:{yesterday}:l")
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:m")
    statements = Statements(monkeypatch, storage)

    body = _tap(client, f"d1:s:{d}:p")  # ✓ 🧘 in the day editor, or an old grid

    assert body["text"].endswith("\n\nMysore")
    assert "Last time" not in body["text"]
    assert _rows(body) == [["📝 Details"], ["✓ Done"]]  # nothing to copy over what is there
    assert _data(body, "📝 Details") == f"p1:o:{d}"
    assert statements.names == ["InMemoryDays.upsert"]


# Details (P1)


def test_add_details_opens_the_details_screen(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    yesterday, d = _ymd(_today() - timedelta(days=1)), _ymd(_today())
    _tap(client, f"d1:s:{yesterday}:p")
    _tap(client, f"p1:t:{yesterday}:60")
    saved = _tap(client, f"d1:s:{d}:p")
    statements = Statements(monkeypatch, storage)

    body = _tap(client, _data(saved, "📝 Add details"))

    assert "Practice done 🙏" in body["text"]
    assert body["text"].endswith("Add details? Optional, one tap is enough.")
    assert "Last time" not in body["text"]
    assert _rows(body) == [
        ["Mysore", "Led"],
        ["1:1", "Self-practice"],
        ["⏱ Duration"],
        ["📏 Length"],
        ["✨ How do you feel?"],
        ["📓 Note"],
        ["✓ Done"],
    ]  # no "same as last time", no mood row, no "Open the app"
    assert _data(body, "✨ How do you feel?") == f"k1:o:{d}"
    assert _data(body, "📓 Note") == f"n1:o:{d}:p"
    assert statements.names == ["InMemoryDays.range_with_moon"]


def test_a_detail_tap_is_one_write_and_keeps_the_layout(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    statements = Statements(monkeypatch, storage)

    body = _tap(client, f"p1:c:{d}:m")

    assert _rows(body) == [
        ["✓ Mysore", "Led"],
        ["1:1", "Self-practice"],
        ["🌐 Online", "⏱ Duration"],
        ["📏 Length"],
        ["✨ How do you feel?"],
        ["📓 Note"],
        ["✓ Done", "Remove details"],
    ]
    assert statements.names == ["InMemoryPractices.save"]


def test_the_note_opened_from_the_details_goes_back_to_them(client: TestClient) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:m")

    note = _tap(client, f"n1:o:{d}:p")
    back_data = _data(note, "Back")
    back = _tap(client, back_data)

    assert back_data == f"n1:b:{d}:p"
    assert "✓ Mysore" in _texts(back)
    assert back["text"].endswith("\n\nMysore")


def test_context_online_and_duration_taps(client: TestClient, storage: InMemoryStorage) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")

    body = _tap(client, f"p1:c:{d}:m")
    assert "✓ Mysore" in _texts(body)
    body = _tap(client, _data(body, "🌐 Online"))
    assert "✓ 🌐 Online" in _texts(body)
    durations = _tap(client, f"p1:d:{d}")
    body = _tap(client, _data(durations, "90 min"))

    assert _main(body).endswith("Mysore · online · 90 min")
    practice = _practice(storage)
    assert (practice.context, practice.online, practice.duration_min) == (
        PracticeContext.MYSORE,
        True,
        90,
    )


def test_self_practice_hides_online(client: TestClient, storage: InMemoryStorage) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:l")
    _tap(client, f"p1:n:{d}:1")

    body = _tap(client, f"p1:c:{d}:s")

    assert not any("Online" in t for t in _texts(body))
    assert _practice(storage).online is False


@pytest.mark.parametrize(
    ("preset", "summary"),
    [
        ("☀️ Short → standing", "Short practice"),
        ("½ Primary → Navasana", "Primary → Navasana"),
        ("Full Primary", "Full Primary"),
    ],
)
def test_static_presets(client: TestClient, preset: str, summary: str) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    lengths = _tap(client, f"p1:m:{d}")

    body = _tap(client, _data(lengths, preset))

    assert _main(body).endswith(summary)


def test_custom_half_primary_plus_intermediate(client: TestClient) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    series = _tap(client, f"p1:a:{d}")
    ranges = _tap(client, _data(series, "Intermediate"))

    assert _texts(ranges)[:4] == [
        "Only Intermediate",
        "Primary + Intermediate",
        "Primary, 1st half + Intermediate",
        "Primary, 2nd half + Intermediate",
    ]
    grid = _tap(client, _data(ranges, "Primary, 2nd half + Intermediate"))
    body = _tap(client, _data(grid, "Pasasana"))

    assert _main(body).endswith("Primary, 2nd half + Intermediate → Pasasana")


def test_russian_labels(client: TestClient) -> None:
    d = _ymd(_today("ru"))
    _tap(client, f"d1:s:{d}:p", lang="ru")
    lengths = _tap(client, f"p1:m:{d}", lang="ru")

    full = _tap(client, _data(lengths, "Первая серия целиком"), lang="ru")
    ranges = _tap(client, f"p1:r:{d}:2", lang="ru")
    grid = _tap(client, _data(ranges, "1-я половина первой + вторая"), lang="ru")
    part = _tap(client, _data(grid, "Пашасана"), lang="ru")

    assert _main(full).endswith("Первая серия целиком")
    assert _main(part).endswith("1-я половина первой + вторая → Пашасана")


def test_grid_pages_and_full_series(client: TestClient) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    grid = _tap(client, f"p1:g:{d}:22:0")

    assert _texts(grid)[0] == "Full series"
    assert "▶" in _texts(grid)
    second = _tap(client, _data(grid, "▶"))
    assert "◀" in _texts(second)
    assert grid["text"] == "Last asana in Intermediate:"
    body = _tap(client, _data(grid, "Full series"))
    assert _main(body).endswith("\n\nFull Intermediate")


def test_same_as_last_time_copies_the_previous_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    yesterday, today = _today() - timedelta(days=1), _today()
    _tap(client, f"d1:s:{_ymd(yesterday)}:p")
    _tap(client, f"p1:c:{_ymd(yesterday)}:l")
    _tap(client, f"p1:l:{_ymd(yesterday)}:11:")

    saved = _tap(client, f"d1:s:{_ymd(today)}:p")
    assert "Last time: Led · Full Primary" in saved["text"]
    body = _tap(client, _data(saved, "🔁 Same as last time"))

    # UI-06: the second tap lands on the done screen, not on the details.
    assert "\n\nLed · Full Primary\n\n" in body["text"]
    assert "Mysore" not in _texts(body)
    assert _texts(body)[-1] == "☰ Menu"
    assert len(storage.day_repo.practice_rows) == 2


def test_same_as_last_time_is_one_write_and_the_read_for_the_offer(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    yesterday, d = _ymd(_today() - timedelta(days=1)), _ymd(_today())
    _tap(client, f"d1:s:{yesterday}:p")
    _tap(client, f"p1:c:{yesterday}:m")
    _tap(client, f"d1:s:{d}:p")
    statements = Statements(monkeypatch, storage)

    body = _tap(client, f"p1:s:{d}")

    # Today: whether the one-time reminder offer is still open is in the settings row.
    assert "Want me to ask" in body["text"]
    assert statements.names == ["InMemoryPractices.copy_latest", "InMemoryNotifications.settings"]


def test_same_as_last_time_skips_a_led_class(client: TestClient, storage: InMemoryStorage) -> None:
    # Q27: the line and the button both use the newest practice that was not a led class.
    before, yesterday, today = (_today() - timedelta(days=n) for n in (2, 1, 0))
    _tap(client, f"d1:s:{_ymd(before)}:p")
    _tap(client, f"p1:c:{_ymd(before)}:m")
    _tap(client, f"d1:s:{_ymd(yesterday)}:p")
    _tap(client, f"p1:c:{_ymd(yesterday)}:l")
    _tap(client, f"p1:l:{_ymd(yesterday)}:11:")

    saved = _tap(client, f"d1:s:{_ymd(today)}:p")
    assert "Last time: Mysore" in saved["text"]
    assert "Led" not in saved["text"]
    body = _tap(client, _data(saved, "🔁 Same as last time"))

    assert "\n\nMysore\n\n" in body["text"]
    [copied] = [p for (_, day), p in storage.day_repo.practice_rows.items() if day == today]
    assert copied.context is PracticeContext.MYSORE


def test_last_time_names_the_day_only_when_the_practice_is_old(client: TestClient) -> None:
    # Q296: more than 14 days before the day being logged, as on the reminder.
    old, today = _today() - timedelta(days=15), _today()
    _tap(client, f"d1:s:{_ymd(old)}:p")
    _tap(client, f"p1:c:{_ymd(old)}:m")

    dated = _tap(client, f"d1:s:{_ymd(today)}:p")
    assert f"Last time ({old:%a, %b} {old.day}): Mysore" in dated["text"]

    near = today - timedelta(days=1)  # 14 days after `old`: not old yet
    recent = _tap(client, f"d1:s:{_ymd(near)}:p")
    assert "Last time: Mysore" in recent["text"]


# Done (V)


def test_done_shows_the_summary_the_ways_on_and_the_menu(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:i")
    statements = Statements(monkeypatch, storage)

    body = _tap(client, f"p1:v:{d}")

    assert "\n\n1:1\n\n" in body["text"]
    # Today, reminder never chosen: the one-time offer (PR-10), its answers above the Menu.
    assert body["text"].endswith("🔔 Want me to ask once a day, so logging takes one tap?")
    assert _rows(body) == [
        ["✨ How do you feel?"],
        ["📝 Details", "✏️ Change", "📅 Another day"],
        ["🔔 Yes, remind me", "No, thanks"],
        ["☰ Menu"],
    ]
    data = [b["callback_data"] for b in _buttons(body)]
    assert data[:3] == [f"k1:o:{d}", f"p1:o:{d}", f"d1:o:{d}"]
    assert data[-1] == "w1:m"
    assert statements.names == ["InMemoryDays.range_with_moon", "InMemoryNotifications.settings"]


def test_done_for_another_day_is_one_read_and_has_no_offer(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _ymd(_today() - timedelta(days=2))
    _tap(client, f"d1:s:{d}:p")
    statements = Statements(monkeypatch, storage)

    body = _tap(client, f"p1:v:{d}")

    assert _rows(body) == [
        ["✨ How do you feel?"],
        ["📝 Details", "✏️ Change", "📅 Another day"],
        ["☰ Menu"],
    ]
    assert statements.names == ["InMemoryDays.range_with_moon"]


def test_the_start_time_carries_the_offset_only_outside_my_zone(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """ADR-0044: a start time (recorded in the app) names its city; the offset follows only
    when the practice was somewhere else than my own zone."""
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:m")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone="Asia/Almaty")
    [key] = storage.day_repo.practice_rows
    at_home = replace(_practice(storage), start_time=time(6, 30), timezone="Asia/Almaty")
    storage.day_repo.practice_rows[key] = at_home

    mine = _tap(client, f"p1:v:{d}")
    storage.day_repo.practice_rows[key] = replace(at_home, timezone="Asia/Tashkent")
    elsewhere = _tap(client, f"p1:v:{d}")
    storage.repo.accounts[account.id] = replace(account, timezone=None)
    unknown = _tap(client, f"p1:v:{d}")

    assert "\n\nMysore · 06:30 Almaty\n\n" in mine["text"]
    assert "Mysore · 06:30 Tashkent (UTC+5)" in elsewhere["text"]  # the same clock, not mine
    assert "Mysore · 06:30 Tashkent (UTC+5)" in unknown["text"]


def test_remove_details(client: TestClient, storage: InMemoryStorage) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    body = _tap(client, f"p1:c:{d}:m")

    body = _tap(client, _data(body, "Remove details"))

    assert "Add details?" in body["text"]
    assert "Remove details" not in _texts(body)
    assert "🔁 Same as last time" not in _texts(body)
    assert not any(v.context for v in storage.day_repo.practice_rows.values())


def test_changing_the_status_drops_details_and_details_need_practice(
    client: TestClient, storage: InMemoryStorage
) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:m")

    _tap(client, f"d1:s:{d}:r")
    body = _tap(client, f"p1:c:{d}:m")  # a stale keyboard

    assert storage.day_repo.practice_rows == {}
    assert body["text"].startswith("This day isn't marked as practice anymore.")
    [(day, _)] = storage.day_repo.rows.values()
    assert day.status is DayStatus.REST


def test_practiced_day_editor_leads_back_to_the_details(client: TestClient) -> None:
    # UI-06 E0: the editor has the three choices and no Details row of its own; the ✓ choice
    # opens the practice again.
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")

    body = _tap(client, f"d1:o:{d}")
    again = _tap(client, f"d1:s:{d}:p")

    assert "✓ 🧘 Practiced" in _texts(body)
    assert "📝 Details" not in _texts(body)
    assert again["text"].startswith("✓ Today, ")


def test_every_callback_fits_telegrams_64_bytes() -> None:
    catalog = load_practice_catalog(
        __import__("pathlib").Path(__file__).resolve().parents[3] / "data" / "seed"
    ).catalog
    day = date(2026, 10, 18)
    worst = 0
    for series in catalog.series:
        ranges = [Range(series.number, series.number)]
        if series.number > 1:
            ranges += [
                Range(series.number - 1, series.number, part)
                for part in (None, "first_half", "second_half")
            ]
        for rng in ranges:
            for stop in series.stops:
                data = encode(PracticeCallback("length", day, range=rng, key=stop.key))
                worst = max(worst, len(data.encode()))
                assert decode(data) == PracticeCallback("length", day, range=rng, key=stop.key)
    assert worst <= 64


@pytest.mark.parametrize(
    "data",
    ["p1", "p1:o", "p1:o:20261399", "p1:c:20261018:z", "p1:n:20261018:2", "p1:t:20261018:999",
     "p1:r:20261018:1", "p1:g:20261018:21:0", "p1:g:20261018:00a:0", "p1:l:20261018:1:x",
     "p1:q:20261018", "p2:o:20261018"],
)  # fmt: skip
def test_malformed_practice_callbacks(data: str) -> None:
    assert decode(data) is None


def test_stale_grid_on_a_day_now_resting_answers_with_the_status_screen(
    client: TestClient,
) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"d1:s:{d}:r")

    # A renamed asana key on an old keyboard: InvalidLength, then the day check.
    body = _tap(client, f"p1:l:{d}:11:renamed-asana")

    assert body["text"].startswith("This day isn't marked as practice anymore.")


def test_clear_on_a_day_now_resting_does_not_claim_practiced(client: TestClient) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"d1:s:{d}:m")

    body = _tap(client, f"p1:x:{d}")

    assert body["text"].startswith("This day isn't marked as practice anymore.")


def test_same_as_last_time_is_offered_only_before_details(client: TestClient) -> None:
    # UI-06: on the screen after 🧘 only, with a previous practice and nothing stored yet.
    yesterday, d = _ymd(_today() - timedelta(days=1)), _ymd(_today())
    _tap(client, f"d1:s:{yesterday}:p")
    _tap(client, f"p1:t:{yesterday}:60")
    first = _tap(client, f"d1:s:{d}:p")
    details = _tap(client, f"p1:o:{d}")

    after = _tap(client, f"p1:c:{d}:m")
    again = _tap(client, f"d1:s:{d}:p")

    assert "🔁 Same as last time" in _texts(first)
    assert "🔁 Same as last time" not in _texts(details)
    assert "🔁 Same as last time" not in _texts(after)
    assert "🔁 Same as last time" not in _texts(again)


def test_an_old_same_as_last_button_without_a_previous_practice_says_so(
    client: TestClient,
) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")

    body = _tap(client, f"p1:s:{d}")

    assert body["text"].startswith("Nothing to copy yet")
    assert _texts(body)[:2] == ["Mysore", "Led"]
