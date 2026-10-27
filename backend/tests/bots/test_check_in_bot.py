"""After-practice check-in through the real webhook (PR-06, spec §5): the one-tap mood row on
P and V (today or yesterday, setting on, no check-in yet), the check-in screen K, the tags
screen T, the `/settings` switch, failures, round trips, and the `k1:` / `s1:k` codecs.

The clock is fixed (Mon Oct 19, 11:00 in Almaty) by replacing the app's `SystemClock`.
`check_in_callbacks` and the domain types are imported inside the tests (test-first)."""

import itertools
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FixedClock, InMemoryCheckIns, InMemoryDays, InMemoryStorage
from tristhana.bots.telegram import settings_callbacks
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.practice import Practice, PracticeContext
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ZONE = "Asia/Almaty"
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)  # Mon Oct 19, 11:00 in Almaty
TODAY = date(2026, 10, 19)
MOODS = ["😔", "😕", "😐", "🙂", "😊"]
PROMPT = "How do you feel after practice? Optional."
EXPLAIN = "⚡ Energy: 1 low → 5 high · 🔥 Effort: 1 easy → 5 hard. Tap what fits, all optional."
PICK = "How did body and mind feel? Pick any."
EDIT = "✨ Check-in"
TAG_ROWS = [
    ["Stiff", "Open"],
    ["Strong", "Light"],
    ["Heavy", "Sore muscles"],
    ["Focused", "Calm"],
    ["Scattered", "Steady breath"],
]
CODES = {
    "s": "stiff",
    "o": "open",
    "g": "strong",
    "l": "light",
    "h": "heavy",
    "r": "sore",
    "f": "focused",
    "c": "calm",
    "d": "scattered",
    "b": "steady_breath",
}
_ids = itertools.count(140_000)


@pytest.fixture(autouse=True)
def outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FixedClock:
    fixed = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: fixed)
    return fixed


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def client(storage: InMemoryStorage, clock: FixedClock) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
    )
    with TestClient(create_app(settings, storage)) as c:
        yield c


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str) -> dict[str, Any]:
    return {"id": 42, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _command(client: TestClient, text: str, lang: str = "en") -> Any:
    message = {
        "message_id": 7,
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


def _rows(body: Any) -> list[list[str]]:
    return [[b["text"] for b in row] for row in body["reply_markup"]["inline_keyboard"]]


def _data_rows(body: Any) -> list[list[str]]:
    return [
        [b.get("callback_data", "") for b in row] for row in body["reply_markup"]["inline_keyboard"]
    ]


def _data_of(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if b["text"] == text)


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _me(
    client: TestClient,
    storage: InMemoryStorage,
    zone: str | None = ZONE,
    offer: bool = True,
    lang: str = "en",
    reminder_chosen: bool = True,
) -> Any:
    """Create the account (via /settings), give it a zone and the check-in setting.
    `reminder_chosen`: the one-time practice-reminder offer on V was answered already."""
    _command(client, "/settings", lang)
    [account] = storage.repo.accounts.values()
    account = replace(account, timezone=zone)
    if not offer:
        account = replace(account, offer_check_in=False)  # type: ignore[call-arg]
    storage.repo.accounts[account.id] = account
    if reminder_chosen:
        chosen = replace(DEFAULTS, practice=replace(DEFAULTS.practice, on=False))
        storage.notifications.stored[account.id] = chosen
    return account


def _c(**values: Any) -> Any:
    from tristhana.domain.check_in import CheckIn, CheckInTag

    tags = values.pop("tags", ())
    return CheckIn(**values, tags=frozenset(CheckInTag(t) for t in tags))


def _given(storage: InMemoryStorage, me: Any, day: date, **check_in: Any) -> None:
    """A practiced day, with a check-in when values are given."""
    storage.day_repo.rows[(me.id, day)] = (DayLog(day, DayStatus.PRACTICED), ZONE)
    if check_in:
        storage.day_repo.check_in_rows[(me.id, day)] = _c(**check_in)


def _stored(storage: InMemoryStorage, me: Any, day: date) -> Any:
    return storage.day_repo.check_in_rows.get((me.id, day))


def _mood_row(body: Any) -> list[str] | None:
    """The callback data of the five-emoji row, if the screen has one."""
    for texts, data in zip(_rows(body), _data_rows(body), strict=True):
        if [t.removeprefix("✓ ") for t in texts] == MOODS:
            return data
    return None


def _offered(body: Any, day: date) -> bool:
    row = _mood_row(body)
    if row is None:
        return False
    assert row == [f"k1:m:{_ymd(day)}:{n}" for n in range(1, 6)]
    assert PROMPT in body["text"]
    assert EDIT not in _texts(body)  # the row replaces ✨, never both
    return True


def _only_edit(body: Any, day: date) -> bool:
    return (
        _mood_row(body) is None
        and PROMPT not in body["text"]
        and _data_of(body, EDIT) == f"k1:o:{_ymd(day)}"
    )


# Offering on P (after 🧘) and V (after ✓ Done)


@pytest.mark.parametrize("back", [0, 1])
def test_details_and_done_offer_the_mood_row_for_today_and_yesterday(
    client: TestClient, storage: InMemoryStorage, back: int
) -> None:
    _me(client, storage)
    day = TODAY - timedelta(days=back)

    details = _tap(client, f"d1:s:{_ymd(day)}:p")
    done = _tap(client, f"p1:v:{_ymd(day)}")

    assert "Practice done 🙏" in details["text"]
    assert _offered(details, day)
    assert _offered(done, day)


@pytest.mark.parametrize("back", [2, 3, 30])
def test_older_days_get_only_the_check_in_button(
    client: TestClient, storage: InMemoryStorage, back: int
) -> None:
    _me(client, storage)
    day = TODAY - timedelta(days=back)

    details = _tap(client, f"d1:s:{_ymd(day)}:p")
    done = _tap(client, f"p1:v:{_ymd(day)}")

    assert _only_edit(details, day)
    assert _only_edit(done, day)


def test_with_the_setting_off_only_the_check_in_button(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage, offer=False)

    details = _tap(client, f"d1:s:{_ymd(TODAY)}:p")
    done = _tap(client, f"p1:v:{_ymd(TODAY)}")

    assert _only_edit(details, TODAY)
    assert _only_edit(done, TODAY)


def test_with_a_check_in_the_summary_and_the_button(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _given(storage, me, TODAY, mood=4, energy=4, effort=3, tags=["calm", "light"])

    details = _tap(client, f"p1:o:{_ymd(TODAY)}")
    done = _tap(client, f"p1:v:{_ymd(TODAY)}")

    for body in (details, done):
        assert "🙂 · ⚡ energy 4/5 · 🔥 effort 3/5 · Light, Calm" in body["text"]
        assert _only_edit(body, TODAY)


def test_an_empty_check_in_is_offered_like_none(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _given(storage, me, TODAY)
    storage.day_repo.check_in_rows[(me.id, TODAY)] = _c()

    assert _offered(_tap(client, f"p1:o:{_ymd(TODAY)}"), TODAY)


def test_the_row_stays_after_a_preset_and_a_detail_tap(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    d = _ymd(TODAY)
    _tap(client, f"d1:s:{d}:p")

    preset = _tap(client, f"p1:l:{d}:11:")  # Full Primary
    context = _tap(client, f"p1:c:{d}:m")

    assert _offered(preset, TODAY)
    assert _offered(context, TODAY)


def test_the_row_stays_after_same_as_last_time(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    before = TODAY - timedelta(days=3)
    _given(storage, me, before)
    storage.day_repo.practice_rows[(me.id, before)] = Practice(PracticeContext.LED)
    _tap(client, f"d1:s:{_ymd(TODAY)}:p")

    body = _tap(client, f"p1:s:{_ymd(TODAY)}")

    assert "Led" in body["text"]
    assert _offered(body, TODAY)


def test_with_the_reminder_offer_v_asks_one_question_only(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage, reminder_chosen=False)
    _tap(client, f"d1:s:{_ymd(TODAY)}:p")

    done = _tap(client, f"p1:v:{_ymd(TODAY)}")

    assert "🔔 Want me to ask once a day, so logging takes one tap?" in done["text"]
    assert _only_edit(done, TODAY)  # the check-in waits behind ✨


def test_a_detail_tap_keeps_the_summary_on_an_older_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    old = TODAY - timedelta(days=5)
    _given(storage, me, old, mood=4, tags=["calm"])

    body = _tap(client, f"p1:c:{_ymd(old)}:m")

    assert "🙂 · Calm" in body["text"]
    assert _only_edit(body, old)


def test_a_detail_tap_with_a_check_in_today_shows_it_instead_of_the_row(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = _me(client, storage)
    _given(storage, me, TODAY, effort=2)
    counter = _Reads(monkeypatch, storage.day_repo)

    body = _tap(client, f"p1:t:{_ymd(TODAY)}:90")

    assert "🔥 effort 2/5" in body["text"]
    assert _only_edit(body, TODAY)
    assert counter.reads == []  # the save's statement brings the check-in along


# The caller's own "today" (zone or provisional guess)


# One instant, two dates: Kiritimati (UTC+14) is on Tue Oct 20, Honolulu (UTC-10) on Mon
# Oct 19. Sun Oct 18 is Honolulu's yesterday and Kiritimati's day before yesterday.
EDGE = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
SUN = date(2026, 10, 18)


@pytest.mark.parametrize(
    ("zone", "offered"), [("Pacific/Honolulu", True), ("Pacific/Kiritimati", False)]
)
def test_kiritimati_and_honolulu_differ_on_the_same_instant(
    client: TestClient, storage: InMemoryStorage, clock: FixedClock, zone: str, offered: bool
) -> None:
    _me(client, storage, zone=zone)
    clock.instant = EDGE

    body = _tap(client, f"d1:s:{_ymd(SUN)}:p")

    assert _offered(body, SUN) is offered
    if not offered:
        assert _only_edit(body, SUN)


def test_a_provisional_zone_decides_too(
    client: TestClient, storage: InMemoryStorage, clock: FixedClock
) -> None:
    # No device zone: ru → Moscow. 22:30 UTC on Sun is Mon 01:30 in Moscow.
    _me(client, storage, zone=None, lang="ru")
    clock.instant = datetime(2026, 10, 18, 22, 30, tzinfo=UTC)

    yesterday = _tap(client, f"d1:s:{_ymd(SUN)}:p", lang="ru")
    before = _tap(client, f"d1:s:{_ymd(date(2026, 10, 17))}:p", lang="ru")

    assert _mood_row(yesterday) is not None
    assert "Как ты после практики? По желанию." in yesterday["text"]
    assert _mood_row(before) is None
    assert "✨ Самочувствие" in _texts(before)


# Taps: K and T


def test_a_mood_tap_saves_and_opens_the_check_in_screen(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    d = _ymd(TODAY)
    _tap(client, f"d1:s:{d}:p")

    body = _tap(client, f"k1:m:{d}:4")

    assert _stored(storage, me, TODAY) == _c(mood=4)
    assert EXPLAIN in body["text"]
    rows = _rows(body)
    assert [t.removeprefix("✓ ") for t in rows[_row_index(body, "😔")]] == MOODS
    assert [f"⚡{n}" for n in range(1, 6)] in rows
    assert [f"🔥{n}" for n in range(1, 6)] in rows
    assert _data_of(body, "🏷 Body and mind…") == f"k1:g:{d}"
    assert _data_of(body, "✓ Done") == f"k1:v:{d}"
    assert _data_of(body, "Remove check-in") == f"k1:x:{d}"


def _row_index(body: Any, first: str) -> int:
    return next(i for i, row in enumerate(_rows(body)) if row and row[0].endswith(first))


def test_the_current_value_is_marked_and_tapping_it_again_clears_it(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    d = _ymd(TODAY)
    _given(storage, me, TODAY)

    _tap(client, f"k1:m:{d}:4")
    body = _tap(client, f"k1:e:{d}:3")

    marked = {b["text"]: b["callback_data"] for b in _buttons(body) if b["text"].startswith("✓ ")}
    assert marked["✓ 🙂"] == f"k1:m:{d}:0"
    assert marked["✓ ⚡3"] == f"k1:e:{d}:0"
    assert _data_of(body, "⚡4") == f"k1:e:{d}:4"
    assert _data_of(body, "🔥5") == f"k1:f:{d}:5"
    cleared = _tap(client, f"k1:e:{d}:0")
    assert _stored(storage, me, TODAY) == _c(mood=4)
    assert "✓ ⚡3" not in _texts(cleared)
    assert "⚡3" in _texts(cleared)


def test_effort_is_saved_on_its_own(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _given(storage, me, TODAY, mood=2)

    _tap(client, f"k1:f:{_ymd(TODAY)}:5")

    assert _stored(storage, me, TODAY) == _c(mood=2, effort=5)


def test_remove_is_offered_only_when_a_check_in_exists(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _given(storage, me, TODAY)

    body = _tap(client, f"k1:o:{_ymd(TODAY)}")

    assert EXPLAIN in body["text"]
    assert "Remove check-in" not in _texts(body)
    assert "✓ Done" in _texts(body)


def test_the_tags_screen_toggles_with_a_mark_and_goes_back(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    d = _ymd(TODAY)
    _given(storage, me, TODAY, mood=3)

    tags = _tap(client, f"k1:g:{d}")
    light = _tap(client, f"k1:t:{d}:l:1")
    twice = _tap(client, f"k1:t:{d}:l:1")  # an old message: absolute, so still on once
    calm = _tap(client, f"k1:t:{d}:c:1")
    off = _tap(client, f"k1:t:{d}:l:0")
    back = _tap(client, _data_of(off, "‹ Back"))  # noqa: RUF001

    assert PICK in tags["text"]
    assert _rows(tags) == [*TAG_ROWS, ["‹ Back"]]  # noqa: RUF001
    assert _data_of(tags, "Scattered") == f"k1:t:{d}:d:1"
    assert _data_of(light, "✓ Light") == f"k1:t:{d}:l:0"
    assert _texts(twice).count("✓ Light") == 1
    assert {"✓ Light", "✓ Calm"} <= set(_texts(calm))
    assert "Light" in _texts(off)
    assert "✓ Calm" in _texts(off)
    assert _stored(storage, me, TODAY) == _c(mood=3, tags=["calm"])
    assert _data_of(off, "‹ Back") == f"k1:o:{d}"  # noqa: RUF001
    assert EXPLAIN in back["text"]


def test_done_shows_the_summary_on_the_done_screen(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _given(storage, me, TODAY, mood=5, effort=2, tags=["steady_breath"])

    body = _tap(client, f"k1:v:{_ymd(TODAY)}")

    assert "😊 · 🔥 effort 2/5 · Steady breath" in body["text"]
    assert "📝 Details" in _texts(body)
    assert _only_edit(body, TODAY)


def test_remove_deletes_and_returns_to_the_done_screen(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _given(storage, me, TODAY, mood=1, tags=["sore"])

    body = _tap(client, f"k1:x:{_ymd(TODAY)}")

    assert _stored(storage, me, TODAY) is None
    assert "📝 Details" in _texts(body)
    assert "Sore muscles" not in body["text"]
    assert _only_edit(body, TODAY)  # just removed: not asked again right away
    assert storage.day_repo.rows[(me.id, TODAY)][0].status is DayStatus.PRACTICED


def test_check_in_screens_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, lang="ru")
    d = _ymd(TODAY)
    _given(storage, me, TODAY, mood=4, energy=4, effort=3, tags=["light", "calm"])

    check_in = _tap(client, f"k1:o:{d}", lang="ru")
    tags = _tap(client, f"k1:g:{d}", lang="ru")

    assert "⚡ Энергия: 1 мало → 5 много" in check_in["text"]
    assert "🙂 · ⚡ энергия 4/5 · 🔥 усилие 3/5 · Лёгкость, Спокойствие" in check_in["text"]
    assert "Убрать самочувствие" in _texts(check_in)
    assert "🏷 Тело и ум…" in _texts(check_in)
    assert "Как тело и ум? Отметь, что подходит." in tags["text"]
    assert "✓ Лёгкость" in _texts(tags)
    assert "Ноющие мышцы" in _texts(tags)


# After the reminder's ✅ (PR-10): V decides without reading


class _Reads:
    """Counts the day log's top-level reads (inner calls of the fake don't count)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, days: InMemoryDays) -> None:
        self.reads: list[str] = []
        self.writes: list[str] = []
        depth = [0]
        for name in ("list_range", "range_with_moon", "history"):
            self._wrap(monkeypatch, days, name, self.reads, depth)
        for name in ("save", "set_tag", "delete"):
            self._wrap(monkeypatch, InMemoryCheckIns, name, self.writes, depth)

    @staticmethod
    def _wrap(
        monkeypatch: pytest.MonkeyPatch, owner: Any, name: str, into: list[str], depth: list[int]
    ) -> None:
        original: Callable[..., Any] = getattr(owner, name)

        async def counted(*args: Any, **kwargs: Any) -> Any:
            if depth[0] == 0:
                into.append(name)
            depth[0] += 1
            try:
                return await original(*args, **kwargs)
            finally:
                depth[0] -= 1

        monkeypatch.setattr(owner, name, counted)

    def clear(self) -> None:
        self.reads.clear()
        self.writes.clear()


def test_after_the_reminders_quick_log_v_offers_the_row_with_no_read(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = _me(client, storage)
    old = TODAY - timedelta(days=20)
    _given(storage, me, old)
    storage.day_repo.practice_rows[(me.id, old)] = Practice(PracticeContext.MYSORE)
    counter = _Reads(monkeypatch, storage.day_repo)

    body = _tap(client, f"r1:s:{_ymd(TODAY)}")

    assert body["text"].startswith("✓ Today")
    assert _offered(body, TODAY)
    assert counter.reads == []


def test_p_and_v_need_no_extra_read_and_taps_one_statement(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _me(client, storage)
    d = _ymd(TODAY)
    counter = _Reads(monkeypatch, storage.day_repo)

    details = _tap(client, f"d1:s:{d}:p")
    p_reads = list(counter.reads)
    counter.clear()
    done = _tap(client, f"p1:v:{d}")
    v_reads = list(counter.reads)
    counter.clear()
    _tap(client, f"k1:m:{d}:3")
    mood = (list(counter.reads), list(counter.writes))
    counter.clear()
    _tap(client, f"k1:t:{d}:b:1")
    tag = (list(counter.reads), list(counter.writes))
    counter.clear()
    _tap(client, f"k1:o:{d}")
    opened = (list(counter.reads), list(counter.writes))

    assert _offered(details, TODAY)
    assert _offered(done, TODAY)
    assert p_reads == ["range_with_moon"]  # unchanged from PR-02 (the status read)
    assert v_reads == ["range_with_moon"]
    assert mood == ([], ["save"])  # the upsert's RETURNING renders K
    assert tag == ([], ["set_tag"])
    assert len(opened[0]) == 1
    assert opened[1] == []


# Failures


@pytest.mark.parametrize(
    "data", ["k1:m:{d}:4", "k1:e:{d}:2", "k1:f:{d}:5", "k1:t:{d}:s:1", "k1:o:{d}", "k1:g:{d}"]
)
def test_a_day_no_longer_practiced_shows_the_status_screen(
    client: TestClient, storage: InMemoryStorage, data: str
) -> None:
    me = _me(client, storage)
    d = _ymd(TODAY)
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"d1:s:{d}:r")

    body = _tap(client, data.format(d=d))  # a stale keyboard

    assert body["text"].startswith("This day isn't marked as practice anymore.")
    assert _stored(storage, me, TODAY) is None
    assert storage.day_repo.rows[(me.id, TODAY)][0].status is DayStatus.REST


def test_a_status_change_drops_the_check_in(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    d = _ymd(TODAY)
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"k1:m:{d}:4")

    _tap(client, f"d1:s:{d}:r")
    again = _tap(client, f"d1:s:{d}:p")

    assert _stored(storage, me, TODAY) is None
    assert _offered(again, TODAY)  # back to "no check-in yet"


def test_remove_details_keeps_the_check_in(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    d = _ymd(TODAY)
    _tap(client, f"d1:s:{d}:p")
    _tap(client, f"p1:c:{d}:m")
    _tap(client, f"k1:m:{d}:5")

    body = _tap(client, f"p1:x:{d}")

    assert _stored(storage, me, TODAY) == _c(mood=5)
    assert "😊" in body["text"]
    assert _only_edit(body, TODAY)


def test_a_database_outage_answers_gently(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _given(storage, me, TODAY)
    storage.day_repo.down = True

    body = _tap(client, f"k1:m:{_ymd(TODAY)}:4")

    assert "Sorry, I've hit a small hiccup on my side." in str(body)


# /settings


def test_settings_offer_and_stop_offering(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    shown = _command(client, "/settings")
    off = _tap(client, "s1:k:0")
    stored_off = storage.repo.accounts[me.id].offer_check_in
    on = _tap(client, "s1:k:1")

    assert "✨ Check-in after practice: offered" in shown["text"]
    assert _data_of(shown, "✨ Don't offer") == "s1:k:0"
    assert "✨ Check-in after practice: not offered" in off["text"]
    assert _data_of(off, "✨ Offer") == "s1:k:1"
    assert stored_off is False
    assert "✨ Check-in after practice: offered" in on["text"]
    assert storage.repo.accounts[me.id].offer_check_in is True


def test_settings_line_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, lang="ru")

    shown = _command(client, "/settings", "ru")
    off = _tap(client, "s1:k:0", lang="ru")

    assert "✨ Самочувствие после практики: предлагаю" in shown["text"]
    assert "✨ Не предлагать" in _texts(shown)  # noqa: RUF001
    assert "✨ Самочувствие после практики: не предлагаю" in off["text"]
    assert "✨ Предлагать" in _texts(off)


def test_the_setting_off_still_allows_a_check_in(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, offer=False)
    _given(storage, me, TODAY)

    body = _tap(client, f"k1:m:{_ymd(TODAY)}:2")

    assert _stored(storage, me, TODAY) == _c(mood=2)
    assert EXPLAIN in body["text"]


# Codecs: every k1: / s1:k callback round-trips and fits


def _all_check_in_callbacks(day: date) -> list[str]:
    d = _ymd(day)
    out = [f"k1:{a}:{d}" for a in "ovgx"]
    out += [f"k1:{a}:{d}:{n}" for a in "mef" for n in range(6)]
    out += [f"k1:t:{d}:{code}:{on}" for code in CODES for on in (0, 1)]
    return out


@pytest.mark.parametrize("day", [date(2000, 1, 1), TODAY, date(2099, 12, 31)])
def test_every_check_in_callback_round_trips_and_fits(day: date) -> None:
    from tristhana.bots.telegram import check_in_callbacks

    for data in _all_check_in_callbacks(day):
        cb = check_in_callbacks.decode(data)
        assert cb is not None, data
        assert check_in_callbacks.encode(cb) == data
        assert len(data.encode()) <= 17  # spec §5; Telegram's limit is 64
    assert len(set(_all_check_in_callbacks(day))) == 4 + 18 + 20


@pytest.mark.parametrize("data", ["s1:k:0", "s1:k:1"])
def test_the_settings_switch_round_trips(data: str) -> None:
    cb = settings_callbacks.decode(data)

    assert cb is not None
    assert settings_callbacks.encode(cb) == data
    assert len(data.encode()) <= 64


@pytest.mark.parametrize("data", ["s1:k", "s1:k:2", "s1:k:yes", "s1:k:1:1"])
def test_the_settings_switch_rejects_malformed(data: str) -> None:
    assert settings_callbacks.decode(data) is None


def test_tag_codes_are_unique_and_cover_every_tag() -> None:
    from tristhana.bots.telegram.check_in_callbacks import TAG_CODES
    from tristhana.domain.check_in import CheckInTag

    assert {code: tag.value for code, tag in TAG_CODES.items()} == CODES
    assert set(TAG_CODES.values()) == set(CheckInTag)
    assert all(len(code) == 1 for code in TAG_CODES)
    assert TAG_CODES["d"] is CheckInTag.SCATTERED


@pytest.mark.parametrize(
    "data",
    [None, "", "k1", "k1:o", "k1:o:20261399", "k1:o:19991231", "k1:o:20261018:1",
     "k1:m:20261018", "k1:m:20261018:6", "k1:m:20261018:x", "k1:e:20261018:-1",
     "k1:f:20261018:10", "k1:t:20261018", "k1:t:20261018:s", "k1:t:20261018:z:1",
     "k1:t:20261018:s:2", "k1:t:20261018:stiff:1", "k1:q:20261018", "k2:o:20261018",
     "p1:o:20261018"],
)  # fmt: skip
def test_malformed_check_in_callbacks(data: str | None) -> None:
    from tristhana.bots.telegram import check_in_callbacks

    assert check_in_callbacks.decode(data) is None
