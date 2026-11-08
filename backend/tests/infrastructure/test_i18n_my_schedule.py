# ruff: noqa: RUF001
"""SC-03 copy (spec §2 table, §7, §8; expert item 6): every new key in `bot.ftl` and `app.ftl`
in both languages; the drafted rows; the filter select ("I teach" / «Веду»); RU plurals of the
shift hours (1/2/5) and the seven genitive weekdays of `schedule-shift`; the new `DateArg`
style `long` ("15 ноября" / "15 November"); RU gender-neutral."""

import re
from datetime import date
from pathlib import Path

import pytest

from tristhana.application.ports.i18n import DateArg
from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

ROOT = Path(__file__).resolve().parents[3]
LOCALES: tuple[Locale, ...] = ("en", "ru")
BOT_KEYS = (
    "my-schedule-open",
    "my-schedule-title",
    "my-schedule-filter",
    "my-schedule-teacher-mark",
    "my-schedule-my-moon",
    "schedule-held-moon",
    "schedule-swapped-inline",
    "schedule-covering-for",
    "schedule-shift",
    "my-schedule-empty",
    "my-schedule-none",
    "my-schedule-zone-unknown",
    "my-schedule-more",
    "command-schedule",
)
APP_KEYS = (
    "my-schedule-open",
    "my-schedule-title",
    "my-schedule-filter",
    "my-schedule-teacher-mark",
    "my-schedule-my-moon",
    "schedule-held-moon",
    "schedule-swapped-inline",
    "schedule-covering-for",
    "schedule-shift",
    "my-schedule-empty",
    "my-schedule-zone-unknown",
    "my-schedule-load-failed",
)
SUNDAY = date(2026, 11, 15)
COPY: list[tuple[str, dict[str, str | int], str, str]] = [
    ("my-schedule-open", {}, "🗓 My schedule", "🗓 Моё расписание"),
    (
        "my-schedule-title",
        {"range": "9–15 Nov"},
        "🗓 My schedule, 9–15 Nov",
        "🗓 Моё расписание, 9–15 Nov",
    ),
    ("schedule-swapped-inline", {"day": "Sat 14 Nov"}, "🔁 Sat 14 Nov", "🔁 Sat 14 Nov"),
    (
        "schedule-covering-for",
        {"name": "Dana", "teacher": "Anna"},
        "Dana (for Anna)",
        "Dana (за Anna)",
    ),
    (
        "my-schedule-none",
        {},
        "Your schedule shows the classes of the shalas you join. Ask your shala for its link.",
        "Здесь будут занятия шал, в которые ты вступишь. Попроси у шалы ссылку.",
    ),
    (
        "my-schedule-zone-unknown",
        {"zone": "Berlin (UTC+1)"},
        "Times are in Berlin (UTC+1). Set your city to see your own time.",
        "Время указано по Berlin (UTC+1). Укажи свой город, чтобы видеть своё время.",
    ),
]
FILTERS = {
    "all": ("All", "Все"),
    "teachers": ("👤 My teachers", "Мои учителя"),
    "mine": ("🧑‍🏫 I teach", "🧑‍🏫 Веду"),
}
EMPTY = {
    "teachers": "No classes with your teachers this week.",
    "mine": "You teach no classes this week.",
    "all": "No classes this week.",
}
GENITIVE = {
    1: "понедельника",
    2: "вторника",
    3: "среды",
    4: "четверга",
    5: "пятницы",
    6: "субботы",
    7: "воскресенья",
}


def _flat(text: str) -> str:
    return " ".join(text.replace("⁨", "").replace("⁩", "").split())


def _app_ids(locale: Locale) -> set[str]:
    text = (ROOT / "miniapp" / "src" / "locales" / locale / "app.ftl").read_text()
    return set(re.findall(r"^([a-z][a-z0-9-]*)\s*=", text, flags=re.MULTILINE))


def _shift(locale: Locale, hours: int | float = 1, weekday: int = 7, dir: str = "later") -> str:
    return _flat(
        FluentTranslator().t(
            locale,
            "schedule-shift",
            weekday=weekday,
            date=DateArg(SUNDAY, style="long"),  # pyright: ignore[reportCallIssue]
            where="Yoga Berlin",
            hours=hours,  # pyright: ignore[reportArgumentType]
            dir=dir,
        )
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_every_bot_key_exists(locale: Locale) -> None:
    assert set(BOT_KEYS) - message_ids(locale) == set()


@pytest.mark.parametrize("locale", LOCALES)
def test_every_mini_app_key_exists(locale: Locale) -> None:
    assert set(APP_KEYS) - _app_ids(locale) == set()


def test_the_mini_app_keys_are_in_parity() -> None:
    prefixes = ("my-schedule-", "schedule-")
    en = {i for i in _app_ids("en") if i.startswith(prefixes)}
    ru = {i for i in _app_ids("ru") if i.startswith(prefixes)}

    assert en == ru


@pytest.mark.parametrize(("key", "args", "en", "ru"), COPY)
def test_the_drafted_rows(key: str, args: dict[str, str | int], en: str, ru: str) -> None:
    t = FluentTranslator()

    assert (_flat(t.t("en", key, **args)), _flat(t.t("ru", key, **args))) == (en, ru)


@pytest.mark.parametrize(("f", "labels"), list(FILTERS.items()))
def test_the_filter_select(f: str, labels: tuple[str, str]) -> None:
    t = FluentTranslator()
    en, ru = (
        _flat(t.t("en", "my-schedule-filter", f=f)),
        _flat(t.t("ru", "my-schedule-filter", f=f)),
    )

    assert en == labels[0]
    assert labels[1] in ru
    assert "Мои" not in ru or f == "teachers"


def test_the_staff_filter_is_i_teach_not_mine() -> None:
    t = FluentTranslator()

    assert "Mine" not in t.t("en", "my-schedule-filter", f="mine")
    assert "Мои" not in t.t("ru", "my-schedule-filter", f="mine")


@pytest.mark.parametrize(("f", "text"), list(EMPTY.items()))
def test_the_empty_week_names_the_filter(f: str, text: str) -> None:
    t = FluentTranslator()

    assert _flat(t.t("en", "my-schedule-empty", f=f)) == text
    assert _flat(t.t("ru", "my-schedule-empty", f=f))


@pytest.mark.parametrize(
    ("key", "en", "ru"),
    [
        ("my-schedule-teacher-mark", "👤", "👤"),
        ("my-schedule-my-moon", "🌙", "🌙"),
        ("schedule-held-moon", "· 🌙", "· 🌙"),
    ],
)
def test_the_marks(key: str, en: str, ru: str) -> None:
    t = FluentTranslator()

    assert (_flat(t.t("en", key)), _flat(t.t("ru", key))) == (en, ru)


def test_the_shift_line_in_english() -> None:
    line = _shift("en")

    assert line.startswith("⚠ From ")
    assert "15 November" in line
    assert line.endswith("Yoga Berlin is 1 h later for you")
    assert _shift("en", 2, dir="earlier").endswith("Yoga Berlin is 2 h earlier for you")


def test_the_shift_line_in_russian_uses_the_genitive() -> None:
    assert (
        _shift("ru") == "⚠ С воскресенья, 15 ноября, Yoga Berlin на 1 час позже по твоему времени"
    )


@pytest.mark.parametrize(("weekday", "word"), list(GENITIVE.items()))
def test_the_seven_genitive_weekdays(weekday: int, word: str) -> None:
    assert _shift("ru", weekday=weekday).startswith(f"⚠ С {word}, 15 ноября,")


@pytest.mark.parametrize(("hours", "words"), [(1, "1 час"), (2, "2 часа"), (5, "5 часов")])
def test_the_russian_plurals_of_the_hours(hours: int, words: str) -> None:
    assert f"на {words} раньше" in _shift("ru", hours, dir="earlier")


@pytest.mark.parametrize(("hours", "words"), [(1, "1 h"), (2, "2 h"), (5, "5 h")])
def test_the_english_hours(hours: int, words: str) -> None:
    assert f"is {words} later" in _shift("en", hours)


@pytest.mark.parametrize(("locale", "expected"), [("en", "15 November"), ("ru", "15 ноября")])
def test_date_arg_style_long(locale: Locale, expected: str) -> None:
    from tristhana.infrastructure.i18n.fluent import _format_date  # pyright: ignore[reportPrivateUsage]

    assert _format_date(DateArg(SUNDAY, style="long"), locale) == expected  # pyright: ignore[reportCallIssue]


def test_the_default_date_style_is_unchanged() -> None:
    from tristhana.infrastructure.i18n.fluent import _format_date  # pyright: ignore[reportPrivateUsage]

    assert _format_date(DateArg(SUNDAY), "en") == "Sun, Nov 15"
    assert DateArg(SUNDAY) == DateArg(SUNDAY, False)


def test_the_russian_copy_is_gender_neutral() -> None:
    t = FluentTranslator()
    words = [_flat(t.t("ru", key, **args)) for key, args, _, _ in COPY] + [
        _shift("ru"),
        *(_flat(t.t("ru", "my-schedule-empty", f=f)) for f in EMPTY),
    ]

    for text in words:
        for gendered in ("вступил ", "вступила", "заменил ", "заменила", "сам ", "сама "):
            assert gendered not in text, text
