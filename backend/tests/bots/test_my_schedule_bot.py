# ruff: noqa: RUF001
"""My schedule through the real webhook (SC-03 spec §2, §5, §7, §8; ADR-0035): `/schedule` and
`/classes` (= *I teach*, Q137) in both languages; times in my zone with the label once in the
header and the class's own time as a second label when the offsets differ (Q136); shala names
only with rows of ≥ 2 shalas; filters `c1:m:<week>:<a|t|m>` and paging 0-3, edited in place;
shala buttons to the SC-02 week; my own moon day 🌙 on the day row; row marks (🌙 lead for a
moon cancellation, ❌ for a closure or a manual cancel, ` · 🌙` for a class held on its moon
day, `(moon day) · 🔁 <day>` for a swap); `Dana (for Anna) 👤`; the ⚠ shift line (RU genitive);
the unknown-zone hint; the 3,800-character cut; every datum ≤ 64 bytes; forged data ignored.
Plain text: no `parse_mode`. Real use cases over the in-memory ports.

The clock is frozen on Mon 9 Nov 2026, 08:00 in Almaty, so week 0 is Mon 9 - Sun 15 Nov."""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.application.ports.i18n import DateArg
from tristhana.bots.telegram.shalas_callbacks import short_id
from tristhana.domain.accounts import Account
from tristhana.domain.classes import ClassType, Override, OverrideStatus, Swap
from tristhana.domain.locale import Locale
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Mon 9 Nov, 08:00 Almaty
NOV = {d: date(2026, 11, d) for d in range(1, 31)}
_ids = itertools.count(260_000)


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


def _text_of(body: Any, data: str) -> str:
    return next(b["text"] for b in _buttons(body) if b.get("callback_data") == data)


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if text in b["text"])


def _lines(body: Any) -> list[str]:
    return [
        " ".join(line.replace("⁨", "").replace("⁩", "").split()) for line in body["text"].splitlines()
    ]


def _day(lines: list[str], prefix: str) -> int:
    """The index of the day row starting with `prefix` ("Fri")."""
    return next(i for i, line in enumerate(lines) if line.startswith(prefix))


def _rows_of(lines: list[str], prefix: str) -> list[str]:
    """The class rows under the day row starting with `prefix`."""
    start = _day(lines, prefix) + 1
    out: list[str] = []
    for line in lines[start:]:
        if not any(ch.isdigit() for ch in line[:8]) and not line.startswith(("🌙", "❌")):
            break
        out.append(line)
    return out


def _label(day: date, locale: Locale = "en") -> str:
    return FluentTranslator().t(locale, "day-label", rel="other", date=DateArg(day))


def _me(
    client: TestClient,
    storage: InMemoryStorage,
    lang: str = "en",
    zone: str | None = "Asia/Almaty",
    **kw: Any,
) -> Account:
    _command(client, "/start", lang)
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    storage.repo.accounts[me.id] = replace(me, timezone=zone, **kw)
    return storage.repo.accounts[me.id]


def _person(storage: InMemoryStorage, name: str) -> Account:
    found = next((a for a in storage.repo.accounts.values() if a.display_name == name), None)
    return found or person(storage, str(1000 + len(storage.repo.accounts)), name)


def _shala(
    storage: InMemoryStorage,
    me: Account,
    role: str | None,
    *,
    owner: str = "Anna",
    name: str = "Ashtanga Almaty",
    city: str = "almaty",
    **kw: Any,
) -> UUID:
    """`owner`'s shala with me in `role` (None: a student)."""
    shala = storage.shalas.add_shala(_person(storage, owner).id, name, city, **kw).id
    if role is None:
        storage.shalas.add_student(shala, me.id)
    else:
        storage.shalas.add_staff(shala, me.id, ShalaRole(role))
    return shala


def _follow(storage: InMemoryStorage, me: Account, teacher: str = "Anna") -> Account:
    anna = _person(storage, teacher)
    storage.link_repo.add(me.id, anna.id, primary=True)
    return anna


def _moon(storage: InMemoryStorage, city: str, *days: date) -> None:
    storage.moon_repo.days_by_location[city] = [MoonDay(d, MoonDayKind.PURNIMA) for d in days]


def _ov(on: date, status: OverrideStatus | None = None, **kw: Any) -> Override:
    values: dict[str, Any] = {"moved_to": None, "start": None, "minutes": None, "teacher_id": None}
    values.update(kw)
    return Override(on_date=on, status=status, **values)


# /schedule


def test_schedule_in_english(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None)
    anna = _follow(storage, me)
    storage.schedule.add_class(shala, teacher_id=anna.id)

    body = _command(client, "/schedule")

    assert body["method"] == "sendMessage"
    assert body.get("parse_mode") is None
    lines = _lines(body)
    assert lines[0].startswith("🗓 My schedule, ")
    assert "Times: Almaty (UTC+5)" in lines
    assert sum("UTC+5" in line for line in lines) == 1  # once, in the header
    assert _rows_of(lines, "Mon") == ["06:00–09:30 Mysore · Anna 👤"]  # one shala: no name
    assert "▶" in _texts(body)
    assert _data(body, "▶") == "c1:m:1:a"
    assert "◀" not in _texts(body)


def test_schedule_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    shala = _shala(storage, me, "teacher")
    anna = _follow(storage, me)
    storage.schedule.add_class(shala, teacher_id=anna.id)

    body = _command(client, "/schedule", "ru")

    lines = _lines(body)
    assert lines[0].startswith("🗓 Моё расписание, ")
    assert "Время: Алматы (UTC+5)" in lines
    assert any(line.startswith("06:00–09:30 Майсор · Anna 👤") for line in lines)
    assert "Веду" in _text_of(body, "c1:m:0:m")
    assert "Мои учителя" in _text_of(body, "c1:m:0:t")


def test_no_shala_says_how_to_join(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    body = _command(client, "/schedule")

    assert " ".join(body["text"].split()) == (
        "Your schedule shows the classes of the shalas you join. Ask your shala for its link."
    )


# Filters, paging and the shala buttons


def test_the_filter_buttons_show_what_applies_and_mark_the_current(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _shala(storage, me, None)

    student = _tap(client, "c1:m:0:a")
    _follow(storage, me)
    follower = _tap(client, "c1:m:0:a")
    _shala(storage, me, "teacher", owner="Olga", name="Second")
    staff = _tap(client, "c1:m:0:t")

    assert student["method"] == "editMessageText"
    assert not {"c1:m:0:t", "c1:m:0:m"} & set(_datas(student))
    assert "c1:m:0:t" in _datas(follower)
    assert "c1:m:0:m" not in _datas(follower)
    assert {"c1:m:0:a", "c1:m:0:t", "c1:m:0:m"} <= set(_datas(staff))
    assert "✓" in _text_of(staff, "c1:m:0:t")
    assert "✓" not in _text_of(staff, "c1:m:0:a")
    assert "✓" not in _text_of(staff, "c1:m:0:m")


def test_each_filter_keeps_its_rows(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, "teacher")
    anna = _follow(storage, me)
    boris = _person(storage, "Boris")
    storage.shalas.add_staff(shala, boris.id, ShalaRole.TEACHER)
    storage.schedule.add_class(shala, teacher_id=anna.id, weekdays=frozenset({1}))
    storage.schedule.add_class(
        shala, type=ClassType.LED, teacher_id=boris.id, weekdays=frozenset({1}),
        start=time(18, 0), minutes=90,
    )  # fmt: skip
    storage.schedule.add_class(
        shala, type=ClassType.PRANAYAMA, teacher_id=me.id, weekdays=frozenset({1}),
        start=time(12, 0), minutes=60,
    )  # fmt: skip

    every = _rows_of(_lines(_tap(client, "c1:m:0:a")), "Mon")
    teachers = _rows_of(_lines(_tap(client, "c1:m:0:t")), "Mon")
    mine = _rows_of(_lines(_tap(client, "c1:m:0:m")), "Mon")

    assert [r.split(" ")[1] for r in every] == ["Mysore", "Pranayama", "Led"]
    assert [r.split(" ")[1] for r in teachers] == ["Mysore"]
    assert [r.split(" ")[1] for r in mine] == ["Pranayama"]


@pytest.mark.parametrize(
    ("data", "empty"),
    [
        ("c1:m:0:t", "No classes with your teachers this week."),
        ("c1:m:0:m", "You teach no classes this week."),
        ("c1:m:0:a", "No classes this week."),
    ],
)
def test_an_empty_filtered_week_names_the_filter(
    client: TestClient, storage: InMemoryStorage, data: str, empty: str
) -> None:
    me = _me(client, storage)
    _shala(storage, me, "teacher")
    _follow(storage, me)

    assert empty in _lines(_tap(client, data))


def test_paging_keeps_the_filter(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _shala(storage, me, None)
    _follow(storage, me)

    first = _tap(client, "c1:m:1:t")
    last = _tap(client, "c1:m:3:t")

    assert (_data(first, "◀"), _data(first, "▶")) == ("c1:m:0:t", "c1:m:2:t")
    assert "▶" not in _texts(last)
    assert "16" in _lines(first)[0]  # the week of Mon 16 Nov


def test_the_shala_buttons_open_each_shalas_week(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    almaty = _shala(storage, me, None)
    berlin = _shala(storage, me, None, owner="Boris", name="Yoga Berlin", city="berlin")

    body = _command(client, "/schedule")

    assert _data(body, "Ashtanga Almaty") == f"c1:w:{short_id(almaty)}:0"
    assert _data(body, "Yoga Berlin") == f"c1:w:{short_id(berlin)}:0"


# Times: my zone first, the class's own second (Q136)


def test_a_berlin_class_carries_its_own_time_and_names_its_shala(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    almaty = _shala(storage, me, None)
    anna = _follow(storage, me)
    berlin = _shala(storage, me, None, owner="Boris", name="Yoga Berlin", city="berlin")
    boris = _person(storage, "Boris")
    storage.schedule.add_class(almaty, teacher_id=anna.id, weekdays=frozenset({1}))
    storage.schedule.add_class(
        berlin, type=ClassType.LED, title="Primary", teacher_id=boris.id,
        weekdays=frozenset({1}), start=time(17, 30), minutes=90,
    )  # fmt: skip

    rows = _rows_of(_lines(_command(client, "/schedule")), "Mon")

    assert rows == [
        "06:00–09:30 Mysore · Anna 👤 · Ashtanga Almaty",
        "21:30–23:00 Led Primary · Boris · Yoga Berlin · 17:30 Berlin (UTC+1)",
    ]


def test_a_class_in_my_zone_has_no_second_label(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Astana shares Almaty's zone: no second label, though the city differs."""
    me = _me(client, storage)
    shala = _shala(storage, me, None, name="Astana Shala", city="astana")
    storage.schedule.add_class(shala, weekdays=frozenset({1}))

    rows = _rows_of(_lines(_command(client, "/schedule")), "Mon")

    assert rows == ["06:00–09:30 Mysore"]


def test_a_berlin_viewer_sees_an_almaty_class_on_the_day_before(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """05:00 Tue in Almaty (UTC+5) is 01:00 Tue in Berlin (UTC+1): my time first, the class's
    own second."""
    me = _me(client, storage, zone="Europe/Berlin")
    shala = _shala(storage, me, None)
    storage.schedule.add_class(shala, weekdays=frozenset({2}), start=time(5, 0), minutes=60)

    lines = _lines(_tap(client, "c1:m:0:a"))

    assert "Times: Berlin (UTC+1)" in lines
    assert _rows_of(lines, "Tue") == ["01:00–02:00 Mysore · 05:00 Almaty (UTC+5)"]


# Moon days and row marks (expert items 1-5)


def test_my_moon_day_is_on_the_day_row_and_the_shalas_on_its_rows(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """My calendar (Mysuru) says Thursday; the shala's (Almaty) says Friday. Both show."""
    me = _me(client, storage, moon_location="mysuru")
    shala = _shala(storage, me, None)
    anna = _follow(storage, me)
    _moon(storage, "mysuru", NOV[12])
    _moon(storage, "almaty", NOV[13])
    storage.schedule.add_class(shala, teacher_id=anna.id)

    lines = _lines(_command(client, "/schedule"))

    assert lines[_day(lines, "Thu")] == f"{_label(NOV[12])} 🌙"
    assert lines[_day(lines, "Fri")] == _label(NOV[13])
    assert _rows_of(lines, "Thu") == ["06:00–09:30 Mysore · Anna 👤"]
    assert _rows_of(lines, "Fri") == ["🌙 06:00–09:30 Mysore · Anna 👤 (moon day)"]
    assert not any("Moon day" in line for line in lines)  # no shala day markers (Q142)


def test_closures_and_manual_cancels_lead_with_a_cross(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None)
    cls = storage.schedule.add_class(shala)
    storage.schedule.seed_closure(shala, NOV[10], NOV[10])
    storage.schedule.add_override(cls.id, _ov(NOV[11], OverrideStatus.CANCELLED))

    lines = _lines(_command(client, "/schedule"))

    assert _rows_of(lines, "Tue") == ["❌ 06:00–09:30 Mysore (shala closed)"]
    assert _rows_of(lines, "Wed") == ["❌ 06:00–09:30 Mysore (cancelled)"]


def test_a_class_held_on_its_moon_day_ends_with_a_quiet_moon(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None, moon_policy="open")
    _moon(storage, "almaty", NOV[13])
    storage.schedule.add_class(shala)

    lines = _lines(_command(client, "/schedule"))

    assert _rows_of(lines, "Fri") == ["06:00–09:30 Mysore · 🌙"]
    assert _rows_of(lines, "Thu") == ["06:00–09:30 Mysore"]


def test_hold_anyway_and_pranayama_rows_on_a_moon_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None, moon_policy="pranayama")
    _moon(storage, "almaty", NOV[13])
    mysore = storage.schedule.add_class(shala)
    storage.schedule.add_class(
        shala, type=ClassType.PRANAYAMA, weekdays=frozenset({5}), start=time(9, 45), minutes=60
    )
    storage.schedule.add_class(
        shala, type=ClassType.LED, weekdays=frozenset({5}), start=time(18, 0), minutes=90
    )
    storage.schedule.add_override(mysore.id, _ov(NOV[13], OverrideStatus.HELD))

    rows = _rows_of(_lines(_command(client, "/schedule")), "Fri")

    assert rows == [
        "06:00–09:30 Mysore · 🌙",
        "09:45–10:45 Pranayama · 🌙",
        "🌙 18:00–19:30 Led (moon day)",
    ]


def test_a_swapped_moon_class_names_where_it_went(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None)
    anna = _follow(storage, me)
    _moon(storage, "almaty", NOV[13])
    storage.schedule.add_class(shala, teacher_id=anna.id)
    storage.schedule.swaps[(shala, NOV[13])] = Swap(NOV[13], NOV[14])

    lines = _lines(_command(client, "/schedule"))

    assert _rows_of(lines, "Fri") == [
        f"🌙 06:00–09:30 Mysore · Anna 👤 (moon day) · 🔁 {_label(NOV[14])}"
    ]
    [saturday] = _rows_of(lines, "Sat")
    assert saturday.startswith("06:00–09:30 Mysore · Anna 👤 · 🔁")
    assert f"instead of {_label(NOV[13])}".lower() in saturday.lower()


def test_a_substitute_for_my_teacher(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None)
    anna = _follow(storage, me)
    dana = _person(storage, "Dana")
    storage.shalas.add_staff(shala, dana.id, ShalaRole.TEACHER)
    cls = storage.schedule.add_class(shala, teacher_id=anna.id)
    storage.schedule.add_override(cls.id, _ov(NOV[10], teacher_id=dana.id))

    lines = _lines(_command(client, "/schedule"))

    assert _rows_of(lines, "Tue") == ["06:00–09:30 Mysore · Dana (for Anna) 👤"]


def test_a_substitute_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    shala = _shala(storage, me, None)
    anna = _follow(storage, me)
    dana = _person(storage, "Dana")
    storage.shalas.add_staff(shala, dana.id, ShalaRole.TEACHER)
    cls = storage.schedule.add_class(shala, teacher_id=anna.id)
    storage.schedule.add_override(cls.id, _ov(NOV[10], teacher_id=dana.id))

    body = _command(client, "/schedule", "ru")

    assert "06:00–09:30 Майсор · Dana (за Anna) 👤" in _lines(body)


# The ⚠ shift line (Q140)


def _dst_week(storage: InMemoryStorage, clock: Frozen) -> None:
    clock.instant = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)  # Mon 19 Oct, 08:00 Almaty
    storage.repo.clock.instant = clock.instant


def test_a_dst_week_shows_the_shift(
    client: TestClient, storage: InMemoryStorage, clock: Frozen
) -> None:
    _dst_week(storage, clock)
    me = _me(client, storage)
    shala = _shala(storage, me, None, owner="Boris", name="Yoga Berlin", city="berlin")
    storage.schedule.add_class(
        shala, type=ClassType.LED, weekdays=frozenset({1, 7}), start=time(17, 30), minutes=90,
        starts_on=date(2026, 10, 1),
    )  # fmt: skip

    lines = _lines(_command(client, "/schedule"))

    assert lines[2].startswith("⚠ From ")
    assert "25 October" in lines[2]
    assert lines[2].endswith("Yoga Berlin is 1 h later for you")
    assert "⚠" in lines[_day(lines, "Sun")]
    assert "⚠" not in lines[_day(lines, "Mon")]
    assert _rows_of(lines, "Mon")[0].startswith("20:30–22:00 Led")
    assert _rows_of(lines, "Sun")[0].startswith("21:30–23:00 Led")


def test_a_dst_week_in_russian_uses_the_genitive(
    client: TestClient, storage: InMemoryStorage, clock: Frozen
) -> None:
    _dst_week(storage, clock)
    me = _me(client, storage, "ru")
    shala = _shala(storage, me, None, owner="Boris", name="Yoga Berlin", city="berlin")
    storage.schedule.add_class(
        shala, type=ClassType.LED, weekdays=frozenset({1, 7}), start=time(17, 30), minutes=90,
        starts_on=date(2026, 10, 1),
    )  # fmt: skip

    lines = _lines(_command(client, "/schedule", "ru"))

    assert "⚠ С воскресенья, 25 октября, Yoga Berlin на 1 час позже по твоему времени" in lines


def test_no_shift_line_in_a_quiet_week(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None, owner="Boris", name="Yoga Berlin", city="berlin")
    storage.schedule.add_class(shala, type=ClassType.LED, start=time(17, 30), minutes=90)

    body = _command(client, "/schedule")

    assert "⚠" not in body["text"]


# The unknown zone (Q141)


def test_an_unknown_zone_uses_my_first_shalas_and_offers_my_city(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, zone=None)
    shala = _shala(storage, me, None, owner="Boris", name="Yoga Berlin", city="berlin")
    storage.schedule.add_class(shala, weekdays=frozenset({1}))

    body = _command(client, "/schedule")

    text = " ".join(body["text"].replace("⁨", "").replace("⁩", "").split())
    assert "Times are in Berlin (UTC+1). Set your city to see your own time." in text
    assert any("🏙" in t for t in _texts(body))
    assert _rows_of(_lines(body), "Mon") == ["06:00–09:30 Mysore"]


def test_my_moon_day_shows_with_an_unknown_zone(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, zone=None, moon_location="mysuru")
    _shala(storage, me, None, owner="Boris", name="Yoga Berlin", city="berlin")
    _moon(storage, "mysuru", NOV[12])

    lines = _lines(_command(client, "/schedule"))

    assert lines[_day(lines, "Thu")].endswith("🌙")


# /classes = My schedule with *I teach* (Q137)


def test_classes_opens_my_schedule_with_i_teach(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, "teacher")
    anna = _person(storage, "Anna")
    mine = storage.schedule.add_class(shala, teacher_id=me.id)
    led = storage.schedule.add_class(
        shala, type=ClassType.LED, teacher_id=anna.id, weekdays=frozenset({2}), start=time(7, 0),
        minutes=90,
    )  # fmt: skip
    storage.schedule.add_class(
        shala, type=ClassType.PRANAYAMA, teacher_id=anna.id, weekdays=frozenset({3}),
        start=time(10, 0), minutes=60,
    )  # fmt: skip
    storage.schedule.add_override(mine.id, _ov(NOV[9], teacher_id=anna.id))
    storage.schedule.add_override(led.id, _ov(NOV[10], teacher_id=me.id))

    body = _command(client, "/classes")

    assert body["method"] == "sendMessage"
    assert body.get("parse_mode") is None
    lines = _lines(body)
    assert lines[0].startswith("🗓 My schedule, ")
    assert "Times: Almaty (UTC+5)" in lines
    assert "✓" in _text_of(body, "c1:m:0:m")
    assert "06:00–09:30 Mysore · Anna is covering" in lines
    assert "07:00–08:30 Led · you're covering for Anna" in lines
    assert not any("Pranayama" in line for line in lines)


def test_classes_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    shala = _shala(storage, me, "teacher")
    anna = _person(storage, "Anna")
    mine = storage.schedule.add_class(shala, teacher_id=me.id)
    storage.schedule.add_override(mine.id, _ov(NOV[9], teacher_id=anna.id))

    lines = _lines(_command(client, "/classes", "ru"))

    assert lines[0].startswith("🗓 Моё расписание, ")
    assert "06:00–09:30 Майсор · тебя заменяет Anna" in lines


def test_classes_for_a_student_names_the_empty_filter(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None)
    storage.schedule.add_class(shala, teacher_id=_person(storage, "Anna").id)

    body = _command(client, "/classes")

    assert "You teach no classes this week." in _lines(body)


def test_schedule_is_in_help_and_the_command_menu(client: TestClient) -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "tools" / "telegram" / "set_webhook.py"
    spec = importlib.util.spec_from_file_location("set_webhook", path)
    assert spec is not None
    assert spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    assert "schedule" in tool.COMMANDS
    assert "/schedule" in _command(client, "/help")["text"]


# Size, data, answers


def test_a_crowded_week_is_cut_at_the_budget(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    for name in ("Ш" * 64, "Щ" * 64):
        shala = _shala(storage, me, "teacher", owner="Olga", name=name)
        for i in range(40):
            storage.schedule.add_class(
                shala, type=ClassType.LED, title="T" * 48, teacher_id=me.id,
                weekdays=frozenset(range(1, 8)), start=time(5 + i % 15, 0), minutes=60,
            )  # fmt: skip

    body = _command(client, "/schedule")

    assert len(body["text"]) <= 4096
    assert "…" in _lines(body)
    assert _lines(body)[-1] == "The full week is in the app."  # review fix: say where the rest is


def test_every_datum_fits_64_bytes(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _shala(storage, me, "admin", name="Ш" * 64)
    _shala(storage, me, None, owner="Boris", name="Щ" * 64, city="berlin")
    _follow(storage, me)

    bodies = [_command(client, "/schedule"), _command(client, "/classes")] + [
        _tap(client, f"c1:m:{week}:{f}") for week in range(4) for f in "atm"
    ]

    datas = [d for body in bodies for d in _datas(body)]
    assert any(d.startswith("c1:m:") for d in datas)
    assert all(len(d.encode()) <= 64 for d in datas), max(datas, key=len)
    assert all(len(d.encode()) == 8 for d in datas if d.startswith("c1:m:"))


def test_a_tap_is_answered_and_edits_in_place(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    _shala(storage, me, None)
    outbound.clear()

    body = _tap(client, "c1:m:1:a")

    assert body["method"] == "editMessageText"
    assert [s.name for s in outbound] == ["answerCallbackQuery"]


@pytest.mark.parametrize("data", ["c1:m:9:z", "c1:m:4:a", "c1:m:0:x", "c1:m:-1:a", "c1:m:0"])
def test_forged_data_is_ignored(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent], data: str
) -> None:
    me = _me(client, storage)
    _shala(storage, me, None)
    storage.schedule.reads.clear()
    outbound.clear()

    body = _tap(client, data)

    assert body is None
    assert "member_windows" not in storage.schedule.reads
    assert [s.name for s in outbound] == ["answerCallbackQuery"]


def test_memberships_are_re_read_on_every_tap(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = _shala(storage, me, None)
    storage.schedule.add_class(shala, title="Early", weekdays=frozenset({1}))

    before = _tap(client, "c1:m:0:a")
    del storage.shalas.students_rows[(shala, me.id)]
    after = _tap(client, "c1:m:0:a")

    assert "Early" in before["text"]
    assert "Early" not in after["text"]
