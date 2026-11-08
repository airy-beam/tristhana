# ruff: noqa: RUF001
"""The teacher view through the real webhook (ST-06, spec §2, §5, §8): the list's marks, the card
in both languages, nothing of a rest's kind and no third state, the last-asana line, the consent
callback change (`t1:a` accepts, `t1:y` only re-renders), Back, forged ids, sizes and the order
of the answer. Real use cases over the in-memory port, with a frozen clock."""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FixedClock, InMemoryStorage
from tests.teacher_link_fakes import add_person
from tristhana.domain.accounts import DISPLAY_NAME_MAX, Account
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.practice import Practice, PracticeLength
from tristhana.domain.progression import STANDING_ONLY, Position, Progression
from tristhana.domain.rest_periods import RestPeriod
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
CODE = "aB3dE6gH9jK2mN5p"
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)  # a Saturday
TODAY = date(2026, 11, 7)
LINKED = date(2026, 6, 1)
LENGTH = PracticeLength(("primary",), "navasana")
_ids = itertools.count(160_000)
_people = itertools.count(5_000)

LEAKS = (
    "🌙",
    "🌸",
    "🤒",
    "✈",
    "🌱",
    "Moon",
    "Ladies",
    "Sick",
    "Travel",
    "No practice",
    "Лунный",
    "Женские",
    "Болезнь",
    "В дороге",
    "Без практики",
)
NOTE_EN = "Not every day gets logged, rest days included. A blank says nothing about the practice."
NOTE_RU = (
    "Не каждый день попадает в журнал, в том числе дни отдыха. Пустой день ничего не говорит о "
    "практике."
)
QUIET_EN = "Nothing shared for a while"
QUIET_RU = "Какое-то время показать нечего"


def _ago(days: int) -> date:
    return TODAY - timedelta(days=days)


@dataclass
class Sent:
    name: str
    fields: dict[str, Any]


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def order() -> list[str]:
    return []


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch, order: list[str]) -> list[Sent]:
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        sent.append(Sent(method.__api_method__, method.model_dump()))
        order.append(method.__api_method__)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FixedClock:
    fixed = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: fixed)
    return fixed


@pytest.fixture
def client(
    storage: InMemoryStorage, clock: FixedClock, outbound: list[Sent]
) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
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
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if text in b["text"])


def _lines(body: Any) -> list[str]:
    return [line for line in body["text"].split("\n") if line.strip()]


def _flat(text: str) -> str:
    return " ".join(text.split())


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Account:
    _command(client, "/start", lang)
    return next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")


def _student(
    storage: InMemoryStorage,
    me: Account,
    name: str | None = "Anna",
    zone: str | None = "UTC",
    agreed: bool = False,
    linked_on: date = LINKED,
) -> Account:
    student = add_person(storage.repo, str(next(_people)), name, "en", zone)
    storage.teacher_links.add(student.id, me.id, linked_on=linked_on, quiet_note_agreed=agreed)
    return student


def _log(storage: InMemoryStorage, who: Account, day: date, status: DayStatus) -> None:
    storage.day_repo.rows[(who.id, day)] = (DayLog(day, status), who.timezone)


def _practiced(
    storage: InMemoryStorage, who: Account, day: date, length: PracticeLength = LENGTH
) -> None:
    _log(storage, who, day, DayStatus.PRACTICED)
    storage.day_repo.practice_rows[(who.id, day)] = Practice(length=length)


def _position(storage: InMemoryStorage, who: Account, position: Position) -> None:
    storage.day_repo.progression_rows[who.id] = Progression(position)


def _card(client: TestClient, who: Account, lang: str = "en") -> Any:
    return _tap(client, f"t1:v:{who.id}:0", lang)


def _teacher(storage: InMemoryStorage, name: str = "Лена", code: str = CODE) -> Account:
    teacher = add_person(storage.repo, str(next(_people)), name)
    storage.teacher_links.codes[teacher.id] = code
    return teacher


# The list


def test_the_list_has_todays_marks_and_a_blank_is_the_bare_name(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    anna, _, maria = (_student(storage, me, n) for n in ("Anna", "Dmitry", "Maria"))
    _practiced(storage, anna, TODAY)
    _log(storage, maria, TODAY, DayStatus.REST)

    body = _tap(client, "t1:s:0")

    assert _texts(body)[:3] == ["🧘 Anna", "Dmitry", "😌 Maria"]
    assert _lines(body) == ["👥 My students (3)", "Days follow each student's own time zone."]
    assert body["method"] == "editMessageText"


def test_the_list_header_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    _student(storage, me)

    body = _tap(client, "t1:s:0", "ru")

    assert _lines(body) == [
        "👥 Мои ученики (1)",
        "Дни считаются по часовому поясу каждого ученика.",
    ]


def test_the_list_opens_from_teachers_as_before(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _student(storage, me)

    screen = _command(client, "/teachers")

    assert _data(screen, "👥 My students (1)") == "t1:s:0"


@pytest.mark.parametrize(
    "status",
    [DayStatus.MOON, DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL],
    ids=lambda s: s.value,
)
def test_every_rest_kind_has_the_one_mark(
    client: TestClient, storage: InMemoryStorage, status: DayStatus
) -> None:
    me = _me(client, storage)
    _log(storage, _student(storage, me), TODAY, status)

    assert _texts(_tap(client, "t1:s:0"))[0] == "😌 Anna"


def test_no_practice_today_is_the_bare_name(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _log(storage, _student(storage, me), TODAY, DayStatus.SKIPPED)

    assert _texts(_tap(client, "t1:s:0"))[0] == "Anna"


def test_a_rest_period_today_has_the_rest_mark(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    student = _student(storage, me)
    storage.day_repo.periods.rows[(student.id, _ago(1))] = RestPeriod(
        _ago(1), TODAY + timedelta(days=2), DayStatus.LADIES
    )

    assert _texts(_tap(client, "t1:s:0"))[0] == "😌 Anna"


def test_the_list_uses_each_students_own_today_never_the_teachers(
    client: TestClient, storage: InMemoryStorage, clock: FixedClock
) -> None:
    """10:30 UTC: Kiritimati is on Nov 8 and Honolulu on Nov 7, each just past midnight."""
    clock.instant = datetime(2026, 11, 7, 10, 30, tzinfo=UTC)
    me = _me(client, storage)
    east = _student(storage, me, "East", "Pacific/Kiritimati")
    west = _student(storage, me, "West", "Pacific/Honolulu")
    _log(storage, east, date(2026, 11, 8), DayStatus.REST)
    _log(storage, west, date(2026, 11, 7), DayStatus.PRACTICED)

    assert _texts(_tap(client, "t1:s:0"))[:2] == ["😌 East", "🧘 West"]


def test_the_order_is_by_name_whatever_the_activity(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _student(storage, me, "Anna")
    boris = _student(storage, me, "boris")
    _student(storage, me, "Clara")
    _practiced(storage, boris, TODAY)

    assert _texts(_tap(client, "t1:s:0"))[:3] == ["Anna", "🧘 boris", "Clara"]


def test_ten_per_page_with_buttons_that_keep_the_page(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    students = [_student(storage, me, f"S{n:02d}") for n in range(12)]

    second = _tap(client, "t1:s:1")

    assert _data(second, "S10") == f"t1:v:{students[10].id}:1"
    assert _data(second, "◀") == "t1:s:0"
    assert "▶" not in _texts(second)


def test_with_no_students_the_list_says_so(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    body = _tap(client, "t1:s:0")

    assert body["text"] == "No students on your list."
    assert storage.teacher_view.reads == ["page"]  # an empty first page isn't a stale one


def test_a_stale_page_reads_twice_and_a_good_one_once(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _student(storage, me)

    _tap(client, "t1:s:0")
    assert storage.teacher_view.reads == ["page"]
    storage.teacher_view.reads.clear()
    body = _tap(client, "t1:s:7")

    assert storage.teacher_view.reads == ["page", "page"]
    assert "Anna" in _texts(body)


def test_the_quiet_note_is_never_on_the_list(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _student(storage, me, agreed=True)

    body = _tap(client, "t1:s:0")

    assert QUIET_EN not in f"{body['text']} {_texts(body)}"


# The card


def _full_card(storage: InMemoryStorage, me: Account) -> Account:
    student = _student(storage, me)
    _position(storage, student, Position("intermediate", "pasasana"))
    _practiced(storage, student, TODAY)
    _log(storage, student, _ago(1), DayStatus.REST)
    return student


def test_the_card_in_english(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    student = _full_card(storage, me)

    body = _card(client, student)

    assert body["method"] == "editMessageText"
    assert _lines(body) == [
        "Anna",
        "Last asana, as marked in their log: Pasasana (Intermediate)",
        "Last 7 days",
        "Today, Sat, Nov 7: 🧘 Practiced, Primary → Navasana",
        "Yesterday, Fri, Nov 6: 😌 Rest day",
        "Thu, Nov 5: ·",
        "Wed, Nov 4: ·",
        "Tue, Nov 3: ·",
        "Mon, Nov 2: ·",
        "Sun, Nov 1: ·",
        NOTE_EN,
    ]
    # PR-08 Phase 3: Pasasana has next stops, so the mark button sits above Remove.
    assert _texts(body) == ["🎉 Mark new asana", "Remove…", "‹ Back"]


def test_the_card_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    student = _full_card(storage, me)

    body = _card(client, student, "ru")

    assert _lines(body) == [
        "Anna",
        "Последняя асана по отметкам в журнале: Пашасана (вторая серия)",
        "Последние 7 дней",
        "Сегодня, сб, 7 нояб.: 🧘 Практика, Первая → Навасана",
        "Вчера, пт, 6 нояб.: 😌 День отдыха",
        "чт, 5 нояб.: ·",
        "ср, 4 нояб.: ·",
        "вт, 3 нояб.: ·",
        "пн, 2 нояб.: ·",
        "вс, 1 нояб.: ·",
        NOTE_RU,
    ]
    assert _texts(body) == ["🎉 Отметить новую асану", "Убрать…", "‹ Назад"]


def test_the_card_says_today_for_the_students_today(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Noon UTC: Nov 8 in Kiritimati, whatever the teacher's date is."""
    me = _me(client, storage)
    student = _student(storage, me, zone="Pacific/Kiritimati")
    _log(storage, student, date(2026, 11, 8), DayStatus.REST)

    lines = _lines(_card(client, student))

    assert "Today, Sun, Nov 8: 😌 Rest day" in lines
    assert "Yesterday, Sat, Nov 7: ·" in lines


def test_a_year_end_card_carries_the_year_on_the_days_before_it(
    client: TestClient, storage: InMemoryStorage, clock: FixedClock
) -> None:
    clock.instant = datetime(2027, 1, 2, 12, tzinfo=UTC)
    me = _me(client, storage)
    student = _student(storage, me)

    lines = _lines(_card(client, student))

    assert "Today, Sat, Jan 2: ·" in lines
    assert any("Dec 31, 2026" in line for line in lines)


@pytest.mark.parametrize(
    ("status", "line"),
    [
        (DayStatus.PRACTICED, "Today, Sat, Nov 7: 🧘 Practiced"),
        (DayStatus.REST, "Today, Sat, Nov 7: 😌 Rest day"),
        (DayStatus.MOON, "Today, Sat, Nov 7: 😌 Rest day"),
        (DayStatus.LADIES, "Today, Sat, Nov 7: 😌 Rest day"),
        (DayStatus.SICK, "Today, Sat, Nov 7: 😌 Rest day"),
        (DayStatus.TRAVEL, "Today, Sat, Nov 7: 😌 Rest day"),
        (DayStatus.SKIPPED, "Today, Sat, Nov 7: ·"),
    ],
    ids=lambda v: v.value if isinstance(v, DayStatus) else "",
)
def test_each_status_reads_as_one_of_three_lines(
    client: TestClient, storage: InMemoryStorage, status: DayStatus, line: str
) -> None:
    me = _me(client, storage)
    student = _student(storage, me)
    _log(storage, student, TODAY, status)

    assert line in _lines(_card(client, student))


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_no_private_mark_or_word_reaches_the_screens(
    client: TestClient, storage: InMemoryStorage, lang: str
) -> None:
    me = _me(client, storage, lang)
    student = _student(storage, me)
    for n, status in enumerate(DayStatus):
        _log(storage, student, _ago(n), status)

    screens = [_tap(client, "t1:s:0", lang), _card(client, student, lang)]

    for screen in screens:
        seen = f"{screen['text']} {_texts(screen)}"
        assert [leak for leak in LEAKS if leak in seen] == []


def test_a_blank_day_reads_the_same_for_no_practice_and_unlogged(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    tapped, silent = _student(storage, me, agreed=True), _student(storage, me, agreed=True)
    for n in range(21):
        _log(storage, tapped, _ago(n), DayStatus.SKIPPED)

    first, second = _card(client, tapped), _card(client, silent)

    assert first["text"] == second["text"]
    assert QUIET_EN in first["text"]


def test_a_card_says_nothing_of_a_main_teacher(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    student = _full_card(storage, me)
    storage.teacher_links.rows[(student.id, me.id)].is_primary = True

    body = _card(client, student)

    seen = f"{body['text']} {_texts(body)}".lower()
    assert "main" not in seen
    assert "⭐" not in seen


def test_the_card_has_no_figure_of_any_kind(client: TestClient, storage: InMemoryStorage) -> None:
    """No run, count or consistency: the only digits are the dates and "Last 7 days"."""
    me = _me(client, storage)
    student = _full_card(storage, me)

    lines = _lines(_card(client, student))

    assert [line for line in lines[:2] + lines[-1:] if any(c.isdigit() for c in line)] == []


# The quiet note


def test_the_quiet_line_comes_last_when_the_flag_is_true(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    student = _student(storage, me, agreed=True)

    assert _lines(_card(client, student))[-2:] == [NOTE_EN, QUIET_EN]


def test_the_quiet_line_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    student = _student(storage, me, agreed=True)

    assert _lines(_card(client, student, "ru"))[-2:] == [NOTE_RU, QUIET_RU]


def test_with_the_flag_false_the_card_is_the_same_but_for_that_line(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    agreed, older = _student(storage, me, agreed=True), _student(storage, me, agreed=False)

    with_note, without = _lines(_card(client, agreed)), _lines(_card(client, older))

    assert with_note == [*without, QUIET_EN]


def test_no_note_with_a_shown_day_in_the_window(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    student = _student(storage, me, agreed=True)
    _log(storage, student, _ago(20), DayStatus.SICK)

    assert QUIET_EN not in _card(client, student)["text"]


# The last-asana line


@pytest.mark.parametrize(
    ("lang", "line"),
    [
        ("en", "Last asana, as marked in their log: Navasana (Primary)"),
        ("ru", "Последняя асана по отметкам в журнале: Навасана (первая серия)"),
    ],
)
def test_the_last_asana_carries_the_series(
    client: TestClient, storage: InMemoryStorage, lang: str, line: str
) -> None:
    me = _me(client, storage, lang)
    student = _student(storage, me)
    _position(storage, student, Position("primary", "navasana"))

    assert _lines(_card(client, student, lang))[1] == line


@pytest.mark.parametrize(
    ("lang", "line"),
    [
        ("en", "As marked in their log: sun salutations and standing"),
        ("ru", "По отметкам в журнале: Сурья Намаскар и стоячие"),
    ],
)
def test_standing_only_has_its_own_line(
    client: TestClient, storage: InMemoryStorage, lang: str, line: str
) -> None:
    me = _me(client, storage, lang)
    student = _student(storage, me)
    _position(storage, student, STANDING_ONLY)

    assert _lines(_card(client, student, lang))[1] == line


def test_a_null_position_omits_the_line(client: TestClient, storage: InMemoryStorage) -> None:
    """PR-08 Phase 3: the neutral unset line instead, and no mark button."""
    me = _me(client, storage)
    student = _student(storage, me)

    body = _card(client, student)
    lines = _lines(body)

    assert lines[:3] == [
        "Anna",
        "No last asana set yet. Once they set it in My asanas, you can mark new ones here.",
        "Last 7 days",
    ]
    assert not any("as marked in their log" in line.lower() for line in lines)
    assert _texts(body) == ["Remove…", "‹ Back"]


@pytest.mark.parametrize(
    ("position", "line"),
    [
        (
            Position("intermediate", "gone-asana"),
            "Last asana, as marked in their log: gone-asana (Intermediate)",
        ),
        (
            Position("gone-series", "gone-asana"),
            "Last asana, as marked in their log: gone-asana (gone-series)",
        ),
    ],
    ids=["stale-key", "stale-series"],
)
def test_a_stale_position_prints_the_raw_value(
    client: TestClient, storage: InMemoryStorage, position: Position, line: str
) -> None:
    me = _me(client, storage)
    student = _student(storage, me)
    _position(storage, student, position)

    assert _lines(_card(client, student))[1] == line


def test_a_stale_length_stays_readable(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    student = _student(storage, me)
    _practiced(storage, student, TODAY, PracticeLength(("gone-series",)))

    assert "Today, Sat, Nov 7: 🧘 Practiced, gone-series" in _lines(_card(client, student))


def test_a_practiced_day_with_no_length_has_no_comma(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    student = _student(storage, me)
    _log(storage, student, TODAY, DayStatus.PRACTICED)

    assert "Today, Sat, Nov 7: 🧘 Practiced" in _lines(_card(client, student))


# Back, old buttons, forged ids


def test_back_keeps_the_page(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    students = [_student(storage, me, f"S{n:02d}") for n in range(12)]
    second = _tap(client, "t1:s:1")

    card = _tap(client, _data(second, "S11"))
    back = _tap(client, _data(card, "‹ Back"))

    assert _data(card, "‹ Back") == "t1:s:1"
    assert _data(back, "S11") == f"t1:v:{students[11].id}:1"


def test_an_old_card_button_still_decodes_and_goes_back_to_page_0(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    student = _student(storage, me)

    body = _tap(client, f"t1:v:{student.id}")

    assert _lines(body)[0] == "Anna"
    assert _data(body, "‹ Back") == "t1:s:0"


def test_remove_still_asks_through_the_old_flow(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    student = _student(storage, me)

    card = _card(client, student)

    assert _data(card, "Remove…") == f"t1:r:{student.id}"
    assert storage.teacher_links.students_of(me.id) == [student.id]


@pytest.mark.parametrize("suffix", ["", ":0", ":3"], ids=["old", "page-0", "page-3"])
def test_a_forged_id_re_renders_the_list(
    client: TestClient, storage: InMemoryStorage, suffix: str
) -> None:
    me = _me(client, storage)
    _student(storage, me)
    stranger = add_person(storage.repo, "9999", "Mallory")
    _log(storage, stranger, TODAY, DayStatus.SICK)

    body = _tap(client, f"t1:v:{stranger.id}{suffix}")

    assert body["method"] == "editMessageText"
    assert "Mallory" not in body["text"]
    assert "Anna" in _texts(body)


def test_a_just_removed_student_re_renders_the_list(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    gone, stays = _student(storage, me, "Gone"), _student(storage, me, "Stays")
    assert stays.id != gone.id
    card = _card(client, gone)
    storage.teacher_links.rows.pop((gone.id, me.id))

    body = _tap(client, _data(card, "‹ Back").replace("t1:s:0", f"t1:v:{gone.id}:0"))

    assert _texts(body)[0] == "Stays"
    assert "Gone" not in body["text"]


@pytest.mark.parametrize("tail", ["x", "-1", "1:2", ""])
def test_a_malformed_card_page_is_only_answered(
    client: TestClient, storage: InMemoryStorage, tail: str
) -> None:
    me = _me(client, storage)
    student = _student(storage, me)

    body = _tap(client, f"t1:v:{student.id}:{tail}")

    assert body is None or body.get("method") == "answerCallbackQuery"


# The answer comes first


@pytest.mark.parametrize("read", ["page", "student"])
def test_the_tap_is_answered_before_the_read_finishes(
    client: TestClient, storage: InMemoryStorage, order: list[str], read: str
) -> None:
    me = _me(client, storage)
    student = _student(storage, me)
    storage.teacher_view.reads = order
    order.clear()

    _tap(client, "t1:s:0" if read == "page" else f"t1:v:{student.id}:0")

    assert order.index("answerCallbackQuery") < order.index(read)


def test_nothing_is_sent_to_the_student_when_a_teacher_looks(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _full_card(storage, me)
    outbound.clear()

    _tap(client, "t1:s:0")
    _card(client, student)

    assert {s.name for s in outbound} == {"answerCallbackQuery"}


# Sizes


def test_every_callback_fits_64_bytes(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    for n in range(500):  # the most a teacher can have: pages reach 49
        _student(storage, me, f"S{n:03d}")

    screens = [_tap(client, "t1:s:49")]
    first = _buttons(screens[0])[0]["callback_data"]
    screens.append(_tap(client, first))

    data = [b["callback_data"] for s in screens for b in _buttons(s) if "callback_data" in b]
    assert first.endswith(":49")
    assert max(len(d.encode()) for d in data) <= 46  # spec §5; Telegram allows 64


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_the_card_fits_one_message_with_64_character_names(
    client: TestClient, storage: InMemoryStorage, lang: str
) -> None:
    longest = "😀" * DISPLAY_NAME_MAX  # two UTF-16 units each, which is what Telegram counts
    me = _me(client, storage, lang)
    student = _student(storage, me, longest, agreed=True)
    _position(storage, student, Position("advanced-a", "gone-" + "x" * 60))
    length = PracticeLength(("primary", "intermediate", "advanced-a"), "x" * 60, "second_half")
    for n in range(7):
        _practiced(storage, student, _ago(n), length)

    body = _card(client, student, lang)

    assert longest in body["text"]
    assert len(body["text"].encode("utf-16-le")) // 2 <= 4096


def test_a_long_name_with_a_mark_still_fits_a_button(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    longest = "Я" * DISPLAY_NAME_MAX
    student = _student(storage, me, longest)
    _practiced(storage, student, TODAY)

    assert _texts(_tap(client, "t1:s:0"))[0] == f"🧘 {longest}"


def test_a_blank_looking_name_uses_the_fallback_on_both_screens(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    student = _student(storage, me, "ㅤ")  # a blank button is refused by Telegram
    _log(storage, student, TODAY, DayStatus.REST)

    assert _texts(_tap(client, "t1:s:0"))[0] == "😌 (no name)"
    assert _lines(_card(client, student))[0] == "(no name)"


# The consent callback


def test_the_new_consent_screens_confirm_creates_the_link_with_the_flag(
    client: TestClient, storage: InMemoryStorage
) -> None:
    teacher = _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")
    assert _data(consent, "✅") == f"t1:a:{CODE}"

    body = _tap(client, _data(consent, "✅"))

    assert body["text"].startswith("✅ Лена is on your list of teachers now.")
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    assert storage.teacher_links.rows[(me.id, teacher.id)].quiet_note_agreed is True


@pytest.mark.parametrize(
    ("lang", "consent_line"),
    [
        ("en", "If nothing shows for a while, Лена sees a short note saying just that."),
        ("ru", "Если какое-то время показать нечего, Лена увидит об этом короткую пометку."),
    ],
)
def test_an_old_confirm_creates_no_link_and_shows_the_current_text(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Sent],
    lang: str,
    consent_line: str,
) -> None:
    teacher = _teacher(storage)
    _me(client, storage, lang)

    body = _tap(client, f"t1:y:{CODE}", lang)

    assert storage.teacher_links.rows == {}
    assert storage.teacher_links.writes == []
    assert consent_line in _flat(body["text"])
    assert body["method"] == "editMessageText"
    assert _data(body, "✅") == f"t1:a:{CODE}"
    assert not [s for s in outbound if s.fields.get("chat_id") == int(_id_of(storage, teacher))]


def _id_of(storage: InMemoryStorage, account: Account) -> str:
    return next(k.provider_user_id for k, v in storage.repo.identities.items() if v == account.id)


def test_tapping_through_an_old_screen_ends_with_the_flag(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Old ✅ re-renders, the new ✅ on the text they can now read confirms."""
    teacher = _teacher(storage)
    me = _me(client, storage)

    shown = _tap(client, f"t1:y:{CODE}")
    assert storage.teacher_links.rows == {}
    _tap(client, _data(shown, "✅"))

    assert storage.teacher_links.rows[(me.id, teacher.id)].quiet_note_agreed is True


def test_an_old_confirm_on_an_existing_link_says_already_and_leaves_the_flag_false(
    client: TestClient, storage: InMemoryStorage
) -> None:
    teacher = _teacher(storage)
    me = _me(client, storage)
    storage.teacher_links.add(me.id, teacher.id)

    body = _tap(client, f"t1:y:{CODE}")

    assert body["text"].startswith("Лена is already on your list of teachers.")
    assert storage.teacher_links.rows[(me.id, teacher.id)].quiet_note_agreed is False


def test_a_new_confirm_on_an_existing_link_leaves_the_flag_false(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """`ON CONFLICT DO NOTHING`: an existing row is never upgraded in place."""
    teacher = _teacher(storage)
    me = _me(client, storage)
    storage.teacher_links.add(me.id, teacher.id)

    body = _tap(client, f"t1:a:{CODE}")

    assert body["text"].startswith("Лена is already on your list of teachers.")
    assert storage.teacher_links.rows[(me.id, teacher.id)].quiet_note_agreed is False


def test_start_on_an_existing_link_changes_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    teacher = _teacher(storage)
    me = _me(client, storage)
    storage.teacher_links.add(me.id, teacher.id)

    body = _command(client, f"/start t_{CODE}")

    assert body["text"].startswith("Лена is already on your list of teachers.")
    assert storage.teacher_links.rows[(me.id, teacher.id)].quiet_note_agreed is False


def test_remove_then_the_new_confirm_gives_the_flag(
    client: TestClient, storage: InMemoryStorage
) -> None:
    teacher = _teacher(storage)
    me = _me(client, storage)
    storage.teacher_links.add(me.id, teacher.id)

    _tap(client, f"t1:x:{teacher.id}")
    _tap(client, f"t1:a:{CODE}")

    assert storage.teacher_links.rows[(me.id, teacher.id)].quiet_note_agreed is True


def test_an_old_confirm_after_a_rotation_says_invalid(
    client: TestClient, storage: InMemoryStorage
) -> None:
    teacher = _teacher(storage)
    _me(client, storage)
    storage.teacher_links.codes[teacher.id] = "Zy8xW7vU6tS5rQ4p"

    body = _tap(client, f"t1:y:{CODE}")

    assert body["text"].startswith("This invite link no longer works.")
    assert storage.teacher_links.rows == {}


def test_the_language_switch_keeps_the_new_confirm(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _teacher(storage)
    _me(client, storage)

    body = _tap(client, f"t1:l:ru:{CODE}")

    assert _data(body, "✅") == f"t1:a:{CODE}"
    assert _data(body, "🗣") == f"t1:l:en:{CODE}"


@pytest.mark.parametrize(
    "data",
    ["t1:s:" + "9" * 59, "t1:s:10000", "t1:s:", f"t1:v:{'0' * 8}-0000-0000-0000-{'0' * 12}:10000"],
)
def test_a_forged_huge_page_never_decodes(data: str) -> None:
    """A page of 59 digits once reached Postgres as an out-of-range offset (ST-06 review)."""
    from tristhana.bots.telegram.teacher_links_callbacks import decode

    assert decode(data) is None


def test_a_four_digit_page_still_decodes() -> None:
    from tristhana.bots.telegram.teacher_links_callbacks import Students, decode

    assert decode("t1:s:9999") == Students(9999)
