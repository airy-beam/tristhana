"""Practice-details screens through the real webhook (PR-02, PR-03, PR-05)."""

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


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if b["text"].endswith(text))


def _practice(storage: InMemoryStorage) -> Any:
    [practice] = storage.day_repo.practice_rows.values()
    return practice


def test_practiced_opens_the_details_screen(client: TestClient) -> None:
    body = _tap(client, f"d1:s:{_ymd(_today())}:p")

    assert "Practice done 🙏" in body["text"]
    assert "Add details? Optional" in body["text"]
    texts = _texts(body)
    assert texts[:4] == ["Mysore", "Led", "1:1", "Self-practice"]
    assert "🔁 Same as last time" not in texts  # nothing to copy yet
    assert {"⏱ Duration", "📏 Length", "✓ Done"} <= set(texts)


def test_context_online_and_duration_taps(client: TestClient, storage: InMemoryStorage) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")

    body = _tap(client, f"p1:c:{d}:m")
    assert "✓ Mysore" in _texts(body)
    body = _tap(client, _data(body, "🌐 Online"))
    assert "✓ 🌐 Online" in _texts(body)
    durations = _tap(client, f"p1:d:{d}")
    body = _tap(client, _data(durations, "90 min"))

    assert body["text"].endswith("Mysore · online · 90 min")
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
        ("☀️ Short: sun salutations, standing, finishing", "Short practice"),
        ("½ Primary → Navasana", "Primary → Navasana"),
        ("Full Primary", "Full Primary"),
    ],
)
def test_static_presets(client: TestClient, preset: str, summary: str) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    lengths = _tap(client, f"p1:m:{d}")

    body = _tap(client, _data(lengths, preset))

    assert body["text"].endswith(summary)


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

    assert body["text"].endswith("Primary, 2nd half + Intermediate → Pasasana")


def test_russian_labels(client: TestClient) -> None:
    d = _ymd(_today("ru"))
    _tap(client, f"d1:s:{d}:p", lang="ru")
    lengths = _tap(client, f"p1:m:{d}", lang="ru")

    full = _tap(client, _data(lengths, "Первая серия целиком"), lang="ru")
    ranges = _tap(client, f"p1:r:{d}:2", lang="ru")
    grid = _tap(client, _data(ranges, "1-я половина первой + вторая"), lang="ru")
    part = _tap(client, _data(grid, "Пашасана"), lang="ru")

    assert full["text"].endswith("Первая серия целиком")
    assert part["text"].endswith("1-я половина первой + вторая → Пашасана")


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
    assert body["text"].endswith("\n\nFull Intermediate")


def test_same_as_last_time_copies_the_previous_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    yesterday, today = _today() - timedelta(days=1), _today()
    _tap(client, f"d1:s:{_ymd(yesterday)}:p")
    _tap(client, f"p1:c:{_ymd(yesterday)}:l")
    _tap(client, f"p1:l:{_ymd(yesterday)}:11:")

    details = _tap(client, f"d1:s:{_ymd(today)}:p")
    assert "Last time: Led · Full Primary" in details["text"]
    body = _tap(client, _data(details, "🔁 Same as last time"))

    assert body["text"].endswith("Led · Full Primary")
    assert len(storage.day_repo.practice_rows) == 2


def test_done_shows_a_summary_with_a_details_button(client: TestClient) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:i")

    body = _tap(client, f"p1:v:{d}")

    assert "\n\n1:1\n\n" in body["text"]
    assert _texts(body)[0] == "📝 Details"
    # Today, reminder never chosen: the one-time offer (PR-10).
    assert body["text"].endswith("🔔 Want me to ask once a day, so logging takes one tap?")
    assert _texts(body)[-2:] == ["🔔 Yes, remind me", "No, thanks"]


def test_remove_details(client: TestClient, storage: InMemoryStorage) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    body = _tap(client, f"p1:c:{d}:m")

    body = _tap(client, _data(body, "Remove details"))

    assert "Add details?" in body["text"]
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


def test_practiced_day_screen_offers_details(client: TestClient) -> None:
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")

    body = _tap(client, f"d1:o:{d}")

    assert "📝 Details" in _texts(body)


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
    yesterday, d = _ymd(_today() - timedelta(days=1)), _ymd(_today())
    _tap(client, f"d1:s:{yesterday}:p")
    _tap(client, f"p1:t:{yesterday}:60")
    first = _tap(client, f"d1:s:{d}:p")

    after = _tap(client, f"p1:c:{d}:m")

    assert "🔁 Same as last time" in _texts(first)
    assert "🔁 Same as last time" not in _texts(after)
