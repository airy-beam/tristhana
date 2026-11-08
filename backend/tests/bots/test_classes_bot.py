# ruff: noqa: RUF001
"""Classes through the real webhook (SC-02 spec §2, §5, §7, §8): the schedule in both
languages with the zone label once in the header, 🌙 and 😌 day rows and a reason on each
cancelled row; a DST week repeating the label on the changed day; ≤ 4096 characters with 40
series and a 64-character shala name; week paging 0-3; staff-only buttons; the 48 h picker →
the ask → cancel, edited in place and silent (Q122); restore and hold anyway; stale and forged
ids re-render; every `c1:` datum ≤ 64 bytes; answered before the write; the shala card's
[🗓 Schedule] and the Q109 day-off adoption (`c1:d`) only for never-chose members of a shala
with a day off. Plain text: no `parse_mode`. Real use cases over the in-memory ports.

The clock is frozen on Mon 9 Nov 2026, 08:00 in Almaty, so week 0 starts on a Monday whether
the implementation counts from the shala's today or from its ISO week."""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.bots.telegram.shalas_callbacks import short_id
from tristhana.domain.accounts import Account
from tristhana.domain.classes import ClassType, Override, OverrideStatus
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.rest_days import DayOff
from tristhana.domain.shalas import ShalaRole
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Mon 9 Nov, 08:00 Almaty
_ids = itertools.count(160_000)


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
def clock() -> Frozen:
    return Frozen()


@pytest.fixture
def storage(clock: Frozen) -> InMemoryStorage:
    storage = shala_storage()
    storage.repo.clock.instant = clock.instant
    return storage


@pytest.fixture
def outbound(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> list[Sent]:
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        sent.append(Sent(method.__api_method__, method.model_dump()))
        storage.schedule.writes.append(method.__api_method__)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


@pytest.fixture
def client(
    storage: InMemoryStorage,
    outbound: list[Sent],
    clock: Frozen,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    import tristhana.main

    monkeypatch.setattr(tristhana.main, "SystemClock", lambda: clock)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url="https://tristhana.web.app",
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
    return [b for row in body.get("reply_markup", {}).get("inline_keyboard", []) for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _datas(body: Any) -> list[str]:
    return [b["callback_data"] for b in _buttons(body) if "callback_data" in b]


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if text in b["text"])


def _lines(body: Any) -> list[str]:
    return [" ".join(line.split()) for line in body["text"].splitlines()]


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Account:
    _command(client, "/start", lang)
    return next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")


def _shala(
    storage: InMemoryStorage,
    me: Account,
    role: str | None,
    *,
    name: str = "Ashtanga Almaty",
    city: str = "almaty",
    days_off: frozenset[int] | None = frozenset({6}),
) -> tuple[UUID, Account]:
    """Anna's shala with me in `role` (None: a student). Returns the shala and Anna."""
    anna = person(storage, "1001", "Anna")
    shala = storage.shalas.add_shala(anna.id, name, city, days_off=days_off).id
    if role is None:
        storage.shalas.add_student(shala, me.id)
    elif role != "nobody":
        storage.shalas.add_staff(shala, me.id, ShalaRole(role))
    return shala, anna


def _week(shala: UUID, week: int = 0) -> str:
    return f"c1:w:{short_id(shala)}:{week}"


def _moon(storage: InMemoryStorage, city: str, *days: date) -> None:
    storage.moon_repo.days_by_location[city] = [MoonDay(d, MoonDayKind.PURNIMA) for d in days]


# The schedule


def test_the_week_in_english(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, anna = _shala(storage, me, None)
    storage.schedule.add_class(shala, teacher_id=anna.id)
    _moon(storage, "almaty", date(2026, 11, 13))

    body = _tap(client, _week(shala))

    assert body["method"] == "editMessageText"
    assert body.get("parse_mode") is None
    lines = _lines(body)
    assert lines[0].startswith("🗓 Ashtanga Almaty: schedule,")
    assert "Times: Almaty (UTC+5)" in lines
    assert "06:00–09:30 Mysore · Anna" in lines
    friday = next(line for line in lines if line.startswith("Fri"))
    assert "🌙 Moon day" in friday
    saturday = next(line for line in lines if line.startswith("Sat"))
    assert "😌 Shala day off" in saturday
    assert any("moon day" in line and "06:00" in line for line in lines[lines.index(friday) :])
    assert sum("UTC+5" in line for line in lines) == 1  # the label once, in the header


def test_the_week_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    shala, anna = _shala(storage, me, None)
    storage.schedule.add_class(shala, teacher_id=anna.id)

    body = _tap(client, _week(shala), "ru")

    lines = _lines(body)
    assert lines[0].startswith("🗓 Ashtanga Almaty: расписание,")
    assert "Время: Алматы (UTC+5)" in lines
    assert "06:00–09:30 Майсор · Anna" in lines


def test_one_to_one_rows_only_for_staff(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)
    storage.schedule.add_class(
        shala, type=ClassType.PRIVATE, title="Private K.", start=time(12, 0), minutes=60
    )

    as_student = _tap(client, _week(shala))
    storage.shalas.add_staff(shala, me.id, ShalaRole.ASSISTANT)
    as_staff = _tap(client, _week(shala))

    assert "Private K." not in as_student["text"]
    assert "Private K." in as_staff["text"]


def test_a_dst_week_repeats_the_label_on_the_changed_day(
    client: TestClient, storage: InMemoryStorage, clock: Frozen
) -> None:
    """Mon 23 Mar 2026 in Berlin: the header says UTC+1; Sun 29 Mar repeats UTC+2."""
    clock.instant = datetime(2026, 3, 23, 6, 0, tzinfo=UTC)
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None, name="Berlin Shala", city="berlin", days_off=None)
    storage.schedule.add_class(
        shala, weekdays=frozenset(range(1, 8)), starts_on=date(2026, 1, 5), start=time(6, 30)
    )

    lines = _lines(_tap(client, _week(shala)))

    assert "Times: Berlin (UTC+1)" in lines
    sunday = next(line for line in lines if line.startswith("Sun"))
    assert "Berlin (UTC+2)" in sunday
    assert sum("UTC+2" in line for line in lines) == 1


def test_forty_series_and_a_long_name_fit_one_message(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, anna = _shala(storage, me, "teacher", name="Ш" * 64)
    for i in range(40):
        storage.schedule.add_class(
            shala,
            type=ClassType.LED,
            title="T" * 48,
            teacher_id=anna.id,
            weekdays=frozenset(range(1, 8)),
            start=time(5 + i % 15, 0),
            minutes=60,
        )

    body = _tap(client, _week(shala))

    assert body["method"] == "editMessageText"
    assert len(body["text"]) <= 4096


def test_an_empty_week(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None, days_off=None)

    body = _tap(client, _week(shala))

    assert "No classes these days." in body["text"]


def test_week_paging(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)

    first = _tap(client, _week(shala, 0))
    last = _tap(client, _week(shala, 3))

    assert _data(first, "▶") == _week(shala, 1)
    assert "◀" not in _texts(first)
    assert _data(last, "◀") == _week(shala, 2)
    assert "▶" not in _texts(last)
    second = _tap(client, _data(first, "▶"))
    assert "16" in _lines(second)[0]  # the week of Mon 16 Nov


@pytest.mark.parametrize(
    ("role", "staff_button"),
    [(None, False), ("assistant", False), ("teacher", True), ("office", True), ("admin", True)],
)
def test_the_cancel_button_is_for_those_who_manage(
    client: TestClient, storage: InMemoryStorage, role: str | None, staff_button: bool
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, role)

    body = _tap(client, _week(shala))

    assert (f"c1:p:{short_id(shala)}" in _datas(body)) is staff_button


# Staff: cancel, restore, hold (within the next 48 h)


def test_the_picker_lists_the_next_48_hours(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")
    cls = storage.schedule.add_class(shala)
    s, c = short_id(shala), short_id(cls.id)

    body = _tap(client, f"c1:p:{s}")

    datas = _datas(body)
    assert f"c1:o:{s}:{c}:20261110" in datas
    assert f"c1:o:{s}:{c}:20261111" in datas  # Wed 06:00 < Wed 08:00
    assert f"c1:o:{s}:{c}:20261112" not in datas


def test_ask_then_cancel_edits_in_place_and_tells_no_one(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")
    cls = storage.schedule.add_class(shala)
    s, c = short_id(shala), short_id(cls.id)
    outbound.clear()

    ask = _tap(client, f"c1:o:{s}:{c}:20261110")
    assert "It shows on the schedule. No one gets a message." in " ".join(ask["text"].split())
    assert storage.schedule.overrides == {}
    done = _tap(client, _data(ask, "❌"))

    assert _data(ask, "❌") == f"c1:x:{s}:{c}:20261110"
    assert done["method"] == "editMessageText"
    assert done["text"].startswith("🗓 Ashtanga Almaty")
    override = storage.schedule.overrides[(cls.id, date(2026, 11, 10))]
    assert override.status is OverrideStatus.CANCELLED
    assert [x.name for x in outbound if x.name == "sendMessage"] == []


def test_restore_a_cancelled_class(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "office")
    cls = storage.schedule.add_class(shala)
    storage.schedule.add_override(cls.id, _ov(date(2026, 11, 10), OverrideStatus.CANCELLED))
    s, c = short_id(shala), short_id(cls.id)

    card = _tap(client, f"c1:o:{s}:{c}:20261110")
    assert _data(card, "↩") == f"c1:r:{s}:{c}:20261110"
    _tap(client, f"c1:r:{s}:{c}:20261110")

    assert storage.schedule.overrides == {}


def test_hold_anyway_on_a_moon_day(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")
    _moon(storage, "almaty", date(2026, 11, 10))
    cls = storage.schedule.add_class(shala)
    s, c = short_id(shala), short_id(cls.id)

    card = _tap(client, f"c1:o:{s}:{c}:20261110")
    assert _data(card, "✅") == f"c1:h:{s}:{c}:20261110"
    _tap(client, f"c1:h:{s}:{c}:20261110")

    held = storage.schedule.overrides[(cls.id, date(2026, 11, 10))]
    assert held.status is OverrideStatus.HELD


def test_hold_anyway_is_offered_only_on_an_auto_cancelled_one(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")
    cls = storage.schedule.add_class(shala)

    card = _tap(client, f"c1:o:{short_id(shala)}:{short_id(cls.id)}:20261110")

    assert not any(t.startswith("✅") for t in _texts(card))


def test_the_tap_is_answered_before_the_write(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")
    cls = storage.schedule.add_class(shala)
    storage.schedule.writes.clear()

    _tap(client, f"c1:x:{short_id(shala)}:{short_id(cls.id)}:20261110")

    order = storage.schedule.writes
    assert order.index("answerCallbackQuery") < order.index("set_override")


@pytest.mark.parametrize("kind", ["o", "x", "r", "h"])
def test_a_stale_class_re_renders(client: TestClient, storage: InMemoryStorage, kind: str) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")
    storage.schedule.writes.clear()

    body = _tap(client, f"c1:{kind}:{short_id(shala)}:{short_id(uuid4())}:20261110")

    assert body["method"] == "editMessageText"
    assert "set_override" not in storage.schedule.writes
    assert "clear_override" not in storage.schedule.writes


@pytest.mark.parametrize("role", [None, "assistant"])
def test_a_forged_cancel_by_someone_who_may_not_writes_nothing(
    client: TestClient, storage: InMemoryStorage, role: str | None
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, role)
    cls = storage.schedule.add_class(shala)

    body = _tap(client, f"c1:x:{short_id(shala)}:{short_id(cls.id)}:20261110")

    assert body["method"] == "editMessageText"
    assert storage.schedule.overrides == {}


def test_a_non_member_sees_no_schedule(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "nobody")
    storage.schedule.add_class(shala, title="Secret")

    body = _tap(client, _week(shala))

    text: str = body["text"] if body else ""
    assert "Secret" not in text
    assert "Ashtanga Almaty" not in text


def test_every_c1_datum_fits_64_bytes(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "admin", name="Ш" * 64)
    _moon(storage, "almaty", date(2026, 11, 10))
    cls = storage.schedule.add_class(shala)
    s, c = short_id(shala), short_id(cls.id)

    screens = [_tap(client, _week(shala, w)) for w in range(4)] + [
        _tap(client, f"c1:p:{s}"),
        _tap(client, f"c1:o:{s}:{c}:20261110"),
    ]

    datas = [d for body in screens for d in _datas(body)]
    assert any(d.startswith("c1:") for d in datas)
    assert all(len(d.encode()) <= 64 for d in datas), max(datas, key=len)


# The shala card: [🗓 Schedule] and the day-off adoption (Q109, Q119)


def _card(client: TestClient, shala: UUID, lang: str = "en") -> Any:
    return _tap(client, f"h1:c:{short_id(shala)}", lang)


def test_the_card_opens_the_schedule(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)

    assert _data(_card(client, shala), "🗓") == _week(shala, 0)


def test_a_never_chose_member_is_offered_the_shalas_day_off(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)

    card = _card(client, shala)

    assert "😌 Day off: Saturday" in _lines(card)
    assert _data(card, "😌 Make Saturday my day off too") == f"c1:d:{short_id(shala)}"
    _tap(client, f"c1:d:{short_id(shala)}")
    assert storage.repo.accounts[me.id].day_off.days == frozenset({6})


def test_the_offer_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    shala, _ = _shala(storage, me, None)

    card = _card(client, shala, "ru")

    assert any(t.startswith("😌 Мой выходной тоже:") for t in _texts(card))


def test_no_offer_for_someone_who_chose(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    storage.repo.accounts[me.id] = replace(me, day_off=DayOff(frozenset({7})))
    shala, _ = _shala(storage, me, None)

    card = _card(client, shala)
    _tap(client, f"c1:d:{short_id(shala)}")  # a stale or forged tap changes nothing

    assert f"c1:d:{short_id(shala)}" not in _datas(card)
    assert storage.repo.accounts[me.id].day_off.days == frozenset({7})


def test_no_offer_when_the_shala_has_no_day_off(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None, days_off=None)

    card = _card(client, shala)

    assert f"c1:d:{short_id(shala)}" not in _datas(card)
    assert not any(line.startswith("😌 Day off") for line in _lines(card))


def _ov(on: date, status: OverrideStatus | None) -> Override:
    return Override(
        on_date=on, status=status, moved_to=None, start=None, minutes=None, teacher_id=None
    )


def test_every_class_moved_off_a_day_gets_its_line(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Mysore and Led both leave a moon Friday for the Saturday day off: two lines on Friday."""
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)
    _moon(storage, "almaty", date(2026, 11, 13))
    storage.schedule.add_class(shala)
    storage.schedule.add_class(
        shala, type=ClassType.LED, weekdays=frozenset({5}), start=time(18, 0), minutes=90
    )
    from tristhana.domain.classes import Swap

    storage.schedule.swaps[(shala, date(2026, 11, 13))] = Swap(
        date(2026, 11, 13), date(2026, 11, 14)
    )

    lines = _lines(_tap(client, _week(shala)))

    friday = lines.index(next(line for line in lines if line.startswith("Fri")))
    moved = [line for line in lines[friday + 1 : friday + 3] if "moved to" in line]
    assert len(moved) == 2
    assert all("(moon day)" in line for line in moved)


def test_paging_survives_a_swapped_day(client: TestClient, storage: InMemoryStorage) -> None:
    """Review fix: the swap lines must not touch the week number behind ◀ and ▶."""
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)
    _moon(storage, "almaty", date(2026, 11, 20))
    storage.schedule.add_class(shala)
    from tristhana.domain.classes import Swap

    storage.schedule.swaps[(shala, date(2026, 11, 20))] = Swap(
        date(2026, 11, 20), date(2026, 11, 21)
    )

    body = _tap(client, _week(shala, 1))

    assert _data(body, "◀") == _week(shala, 0)
    assert _data(body, "▶") == _week(shala, 2)


def test_an_online_class_elsewhere_shows_in_the_shalas_time_and_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Q124: a Berlin 22:00 online class is 02:00 the next day in Almaty."""
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None, days_off=None)
    storage.schedule.add_class(
        shala,
        type=ClassType.LED,
        online=True,
        city="berlin",
        weekdays=frozenset({1}),
        start=time(22, 0),
        minutes=60,
    )

    lines = _lines(_tap(client, _week(shala)))

    tuesday = lines.index(next(line for line in lines if line.startswith("Tue")))
    assert lines[tuesday + 1].startswith("02:00–03:00 Led")


# /classes (SC-03 opens My schedule with *I teach*: see test_my_schedule_bot.py)


def test_classes_is_in_help_and_the_command_menu(client: TestClient) -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "tools" / "telegram" / "set_webhook.py"
    spec = importlib.util.spec_from_file_location("set_webhook", path)
    assert spec is not None
    assert spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    assert "classes" in tool.COMMANDS
    assert "🧑‍🏫 /classes: the classes you teach this week" in _command(client, "/help")["text"]
