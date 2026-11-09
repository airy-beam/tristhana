# ruff: noqa: RUF001
"""Attendance through the real webhook (SC-05 spec §2, §5, §8): the 🙋 list (EN and RU), a
claim patched in place with "🧘 Log this day" (not after Conference, Q196), the day card's date
for a cross-zone class, removal, the staff picker and roster, toggles and "Confirm all"
patched in place from the write's counts, paging, a stale or forged tap, callbacks ≤ 64
bytes, the entry buttons on My schedule and the shala week, the ` · 🙋` row mark, 64-character
names, and the banned words. Clock: Mon 9 Nov 2026, 08:00 Almaty."""

import re
from datetime import UTC, date, datetime, time
from typing import Any

from fastapi.testclient import TestClient

from tests.bots import test_my_schedule_bot as _harness
from tests.bots.test_my_schedule_bot import (  # pyright: ignore[reportPrivateUsage]
    _buttons,  # pyright: ignore[reportPrivateUsage]
    _command,  # pyright: ignore[reportPrivateUsage]
    _datas,  # pyright: ignore[reportPrivateUsage]
    _ids,  # pyright: ignore[reportPrivateUsage]
    _lines,  # pyright: ignore[reportPrivateUsage]
    _me,  # pyright: ignore[reportPrivateUsage]
    _person,  # pyright: ignore[reportPrivateUsage]
    _post,  # pyright: ignore[reportPrivateUsage]
    _shala,  # pyright: ignore[reportPrivateUsage]
    _tap,  # pyright: ignore[reportPrivateUsage]
    _texts,  # pyright: ignore[reportPrivateUsage]
    _user,  # pyright: ignore[reportPrivateUsage]
)
from tests.fakes import InMemoryStorage
from tristhana.bots.telegram import attendance_callbacks as cb
from tristhana.bots.telegram.shalas_callbacks import short_id
from tristhana.domain.attendance import AttendanceState, Snapshot
from tristhana.domain.classes import ClassType

# The harness's fixtures (the real webhook over in-memory ports, a frozen clock).
client = _harness.client
clock = _harness.clock
outbound = _harness.outbound
storage = _harness.storage

MON, SUN = date(2026, 11, 9), date(2026, 11, 8)
EVERY_DAY = frozenset(range(1, 8))
BANNED = re.compile(r"absent|missed|no-show|пропустил|прогул|\bбыл[аи]?\b|\bсам[аи]?\b", re.I)


def _tap_on(client: TestClient, body: Any, data: str, lang: str = "en") -> Any:
    """A tap on a button of `body` (the bot's last screen), with its text and keyboard."""
    message = {
        "message_id": 9,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "text": body["text"],
        "reply_markup": body.get("reply_markup"),
    }
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang),
        "chat_instance": "ci",
        "data": data,
        "message": message,
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _setup(
    client: TestClient, storage: InMemoryStorage, role: str | None, lang: str = "en"
) -> tuple[Any, Any, Any]:
    me = _me(client, storage, lang)
    shala = _shala(storage, me, role)
    mysore = storage.schedule.add_class(shala, weekdays=EVERY_DAY, starts_on=date(2026, 10, 1))
    storage.attendance  # noqa: B018  # attaches the fake to the schedule
    return me, shala, mysore.id


def _check_text(body: Any) -> None:
    assert "parse_mode" not in body or body["parse_mode"] is None
    for b in _buttons(body):
        assert len(b.get("callback_data", "").encode()) <= 64
    everything = " ".join([body["text"], *_texts(body)])
    assert not BANNED.search(everything), everything


def test_my_list_and_a_claim_in_place(client: TestClient, storage: InMemoryStorage) -> None:
    me, _, mysore = _setup(client, storage, None)
    schedule = _command(client, "/schedule")
    assert cb.my_list() in _datas(schedule)
    assert cb.staff_pick() not in _datas(schedule)  # a student

    listing = _tap(client, cb.my_list())

    assert _lines(listing)[0].startswith("🙋 Mark a class you came to")
    texts = _texts(listing)
    assert texts[0].startswith("◻️ ")
    assert "06:00 Mysore · Ashtanga Almaty" in texts[0]
    assert len(texts) == 8  # 7 days + Back
    _check_text(listing)

    claimed = _tap_on(client, listing, cb.mark("i", mysore, MON))

    assert claimed["text"].startswith("🙋 Marked:")
    assert "staff can confirm" in claimed["text"]
    assert storage.attendance.state_of(mysore, MON, me.id) is AttendanceState.CLAIMED
    assert _texts(claimed)[0].startswith("🙋 ")
    assert cb.mark("u", mysore, MON) in _datas(claimed)
    assert "d1:o:20261109" in _datas(claimed)  # 🧘 Log this day → my day card
    assert "🧘 Log this day" in _texts(claimed)
    _check_text(claimed)

    removed = _tap_on(client, claimed, cb.mark("u", mysore, MON))

    assert removed["text"].startswith("Mark removed:")
    assert storage.attendance.rows == {}
    assert _texts(removed)[0].startswith("◻️ ")
    assert "d1:o:20261109" not in _datas(removed)

    # My schedule shows my own mark on the row.
    _tap_on(client, removed, cb.mark("i", mysore, MON))
    week = _command(client, "/schedule")
    assert any(line.endswith("· 🙋") for line in _lines(week))


def test_conference_offers_no_log_day(client: TestClient, storage: InMemoryStorage) -> None:
    _, shala, _ = _setup(client, storage, None)
    conf = storage.schedule.add_class(shala, weekdays=EVERY_DAY, type=ClassType.CONFERENCE,
                                      start=time(7, 0), minutes=60)  # fmt: skip
    listing = _tap(client, cb.my_list())
    claimed = _tap_on(client, listing, cb.mark("i", conf.id, MON))
    assert claimed["text"].startswith("🙋 Marked:")
    assert not any(d.startswith("d1:") for d in _datas(claimed))


def test_log_this_day_targets_my_local_date(client: TestClient, storage: InMemoryStorage) -> None:
    """A Berlin 21:30 online class on Sun 8 Nov is Mon 9 Nov 01:30 for me in Almaty."""
    _, shala, _ = _setup(client, storage, None)
    online = storage.schedule.add_class(shala, weekdays=EVERY_DAY, online=True, city="berlin",
                                        start=time(21, 30), minutes=60)  # fmt: skip
    listing = _tap(client, cb.my_list())
    claimed = _tap_on(client, listing, cb.mark("i", online.id, SUN))
    assert "d1:o:20261109" in _datas(claimed)


def test_russian_list_and_claim(client: TestClient, storage: InMemoryStorage) -> None:
    _, _, mysore = _setup(client, storage, None, "ru")
    listing = _tap(client, cb.my_list(), "ru")
    assert _lines(listing)[0].startswith("🙋 Отметка о посещении")
    claimed = _tap_on(client, listing, cb.mark("i", mysore, MON), "ru")
    assert claimed["text"].startswith("🙋 Отмечено:")
    assert "🧘 Записать этот день" in _texts(claimed)
    _check_text(claimed)


def test_a_closed_occurrence_shows_not_open(client: TestClient, storage: InMemoryStorage) -> None:
    _, _, mysore = _setup(client, storage, None)
    listing = _tap(client, cb.my_list())
    future = cb.mark("i", mysore, date(2026, 11, 10))
    keyboard = {"inline_keyboard": [[{"text": "◻️ x", "callback_data": future}]]}
    body = _tap_on(client, listing | {"reply_markup": keyboard}, future)
    assert body["text"].startswith("This class can't be marked now")


def test_forged_data_does_nothing(client: TestClient, storage: InMemoryStorage) -> None:
    _setup(client, storage, None)
    _tap(client, "v1:i:nope:20261109")
    _tap(client, "v1:y:x")
    assert storage.attendance.rows == {}


def test_staff_picker_roster_and_toggles(client: TestClient, storage: InMemoryStorage) -> None:
    me, shala, mysore = _setup(client, storage, "assistant")
    dana, ilya, vera = (_person(storage, n) for n in ("Dana", "Ilya", "Vera"))
    for p in (dana, ilya, vera):
        storage.shalas.add_student(shala, p.id)
    starts = datetime(2026, 11, 9, 1, tzinfo=UTC)
    snap = Snapshot(shala, mysore, MON, MON, starts, "Asia/Almaty", ClassType.MYSORE)
    storage.attendance.seed(snap, dana.id, AttendanceState.CLAIMED)

    schedule = _command(client, "/schedule")
    assert cb.staff_pick() in _datas(schedule)
    week = _tap(client, f"c1:w:{short_id(shala)}:0")
    assert cb.staff_pick() in _datas(week)

    picker = _tap(client, cb.staff_pick())
    assert _lines(picker)[0] == "📋 Which class? Last 7 days."
    first = _texts(picker)[0]
    assert "Mysore" in first
    assert "✅ 0 · 🙋 1" in first
    _check_text(picker)

    roster = _tap(client, cb.roster("r", mysore, MON))
    lines = _lines(roster)
    assert lines[0].startswith("📋 Mysore · Mon")
    assert "Almaty (UTC+5)" in lines[0]
    assert lines[1] == "Ashtanga Almaty"
    assert lines[2] == "✅ 0 · 🙋 1 to confirm"
    assert _texts(roster)[:3] == ["🙋 Dana", "◻️ Ilya", "◻️ Vera"]
    assert "✅ Confirm all 🙋 (1)" in _texts(roster)
    _check_text(roster)

    marked = _tap_on(client, roster, cb.person("y", mysore, MON, vera.id, 0))
    assert _lines(marked)[2] == "✅ 1 · 🙋 1 to confirm"
    assert "✅ Vera" in _texts(marked)
    assert cb.person("n", mysore, MON, vera.id, 0) in _datas(marked)

    confirmed = _tap_on(client, marked, cb.roster("a", mysore, MON, 0))
    assert _lines(confirmed)[2] == "✅ 2 · nothing to confirm"
    assert "✅ Dana" in _texts(confirmed)
    assert not any(t.startswith("✅ Confirm all") for t in _texts(confirmed))

    unmarked = _tap_on(client, confirmed, cb.person("n", mysore, MON, vera.id, 0))
    assert _lines(unmarked)[2] == "✅ 1 · nothing to confirm"
    assert "◻️ Vera" in _texts(unmarked)
    assert storage.attendance.state_of(mysore, MON, vera.id) is None
    assert storage.attendance.state_of(mysore, MON, me.id) is None


def test_roster_paging_and_long_names(client: TestClient, storage: InMemoryStorage) -> None:
    _, shala, mysore = _setup(client, storage, "office")
    long = "Ж" * 64
    for i in range(9):
        storage.shalas.add_student(shala, _person(storage, f"{long[:60]}{i:02d}").id)
    roster = _tap(client, cb.roster("r", mysore, MON))
    people = [d for d in _datas(roster) if d.startswith("v1:y:")]
    assert len(people) == 8
    assert cb.roster("r", mysore, MON, 1) in _datas(roster)
    page2 = _tap(client, cb.roster("r", mysore, MON, 1))
    assert len([d for d in _datas(page2) if d.startswith("v1:y:")]) == 1
    assert cb.roster("r", mysore, MON, 0) in _datas(page2)
    _check_text(page2)


def test_a_student_on_the_roster_goes_to_the_picker(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _, _, mysore = _setup(client, storage, None)
    body = _tap(client, cb.roster("r", mysore, MON))
    assert _lines(body)[0] == "No classes in the last 7 days."


def test_the_lists_carry_the_zone_label(client: TestClient, storage: InMemoryStorage) -> None:
    """Review: times on the 🙋 list and the staff picker say whose clock they are."""
    _setup(client, storage, "assistant")
    listing = _tap(client, cb.my_list())
    assert _lines(listing)[1].startswith("Times: ")
    assert "(UTC+5)" in _lines(listing)[1]
    picker = _tap(client, cb.staff_pick())
    assert _lines(picker)[1].startswith("Times: ")
    assert "(UTC+5)" in _lines(picker)[1]


def test_an_unknown_zone_says_whose_times_these_are(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, zone=None)
    shala = _shala(storage, me, None)
    storage.schedule.add_class(shala, weekdays=EVERY_DAY, starts_on=date(2026, 10, 1))
    storage.attendance  # noqa: B018
    listing = _tap(client, cb.my_list())
    assert _lines(listing)[1].startswith("Times are in Almaty (UTC+5)")


def test_a_multi_line_title_keeps_the_counts_line(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Review: user text with a newline can't push the counts line off its index."""
    _, shala, _ = _setup(client, storage, "assistant")
    vera = _person(storage, "Vera")
    storage.shalas.add_student(shala, vera.id)
    led = storage.schedule.add_class(shala, weekdays=EVERY_DAY, type=ClassType.LED,
                                     title="Primary\nsecond line", start=time(7, 0),
                                     minutes=90)  # fmt: skip
    roster = _tap(client, cb.roster("r", led.id, MON))
    assert "Primary second line" in _lines(roster)[0]
    assert _lines(roster)[2] == "✅ 0 · nothing to confirm"
    marked = _tap_on(client, roster, cb.person("y", led.id, MON, vera.id, 0))
    assert _lines(marked)[1] == "Ashtanga Almaty"
    assert _lines(marked)[2] == "✅ 1 · nothing to confirm"
