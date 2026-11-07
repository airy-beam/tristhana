# ruff: noqa: RUF001, RUF002
"""MD-02 copy (spec §2): every new key in both languages and on the surfaces the table names,
exactly as accepted; names nominative in RU (in parentheses or after a colon, never after «у»);
RU gender-neutral; no nudges."""

import re
from pathlib import Path

import pytest

from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

ROOT = Path(__file__).resolve().parents[3]
BOT_FTL = ROOT / "backend/src/tristhana/infrastructure/i18n/locales/{}/bot.ftl"
APP_FTL = ROOT / "miniapp/src/locales/{}/app.ftl"
LOCALES: tuple[Locale, ...] = ("en", "ru")

BOTH = (
    "moon-source-teacher",
    "moon-source-teacher-none",
    "moon-follow-teacher",
    "moon-teacher-shared",
)
BOT_ONLY = (
    "settings-moon-line-teacher",
    "moon-follow-changed",
    "moon-follow-ended",
    "invite-moon-hint",
    "moon-teacher-own",
    "moon-keep-city",
    "moon-kept",
    "moon-keep-already",
)

COPY: list[tuple[str, dict[str, str | int], str, str]] = [
    (
        "moon-source-teacher",
        {"name": "Anna"},
        "👥 Same as your main teacher, Anna. You can choose another city.",
        "👥 Как у основного учителя: Anna. Можно выбрать другой город.",
    ),
    (
        "moon-source-teacher-none",
        {"name": "Anna", "city": "Mysuru"},
        "👥 Anna hasn't chosen a city yet, so the dates are for 📍 Mysuru for now.",
        "👥 У учителя (Anna) пока не выбран город, поэтому даты считаются по городу 📍 Mysuru.",
    ),
    (
        "moon-follow-teacher",
        {"name": "Anna"},
        "👥 Follow my teacher (Anna)",
        "👥 Как у учителя (Anna)",
    ),
    (
        "settings-moon-line-teacher",
        {"city": "Almaty", "name": "Anna"},
        "🌙 Moon days: 📍 Almaty (as Anna)",
        "🌙 Лунные дни: 📍 Almaty (как у учителя: Anna)",
    ),
    (
        "moon-follow-changed",
        {"name": "Anna", "city": "Almaty"},
        "🌙 Your moon days now follow Anna: 📍 Almaty. You can change this in /moon.",
        "🌙 Лунные дни теперь как у учителя (Anna): 📍 Almaty. Поменять можно в /moon.",
    ),
    (
        "moon-follow-ended",
        {"city": "Mysuru"},
        "🌙 Your moon days are now for 📍 Mysuru. You can change this in /moon.",
        "🌙 Лунные дни теперь считаются по городу 📍 Mysuru. Поменять можно в /moon.",
    ),
    (
        "moon-teacher-shared",
        {"chosen": "yes", "city": "Almaty"},
        "👥 Students who haven't chosen a city follow yours: 📍 Almaty.",
        "👥 У учеников, которые не выбрали город, лунные дни как у тебя: 📍 Almaty.",
    ),
    (
        "moon-teacher-shared",
        {"chosen": "no", "city": "Mysuru"},
        "👥 Your students' moon days are for 📍 Mysuru, like yours. You can keep it or choose "
        "your city in /moon.",
        "👥 У учеников лунные дни считаются по городу 📍 Mysuru, как и у тебя. Можно оставить "
        "так или выбрать свой город в /moon.",
    ),
    (
        "moon-teacher-shared",
        {"chosen": "follow", "city": "Mysuru"},
        "👥 Your students' moon days are for 📍 Mysuru. You can keep it or choose your city "
        "in /moon.",
        "👥 У учеников лунные дни считаются по городу 📍 Mysuru. Можно оставить так или выбрать "
        "свой город в /moon.",
    ),
    (
        "invite-moon-hint",
        {},
        "Students who haven't chosen a moon city will follow the city you choose in /moon.",
        "У учеников, которые не выбрали город, лунные дни будут считаться по городу, который ты "
        "выберешь в /moon.",
    ),
    (
        "moon-teacher-own",
        {"city": "Mysuru", "kept": "Almaty", "name": "Anna"},
        "🌙 Now that you have students, your moon days follow your own setting: 📍 Mysuru. "
        "To keep 📍 Almaty (as with Anna), tap below.",
        "🌙 Теперь, когда у тебя есть ученики, лунные дни считаются по твоей настройке: "
        "📍 Mysuru. Чтобы оставить 📍 Almaty, как у учителя (Anna), нажми кнопку ниже.",
    ),
    ("moon-keep-city", {"city": "Almaty"}, "Keep 📍 Almaty", "Оставить 📍 Almaty"),
    (
        "moon-kept",
        {"city": "Almaty"},
        "🌙 Done: your moon days stay with 📍 Almaty. You can change this in /moon.",
        "🌙 Готово: лунные дни остаются по городу 📍 Almaty. Поменять можно в /moon.",
    ),
    (
        "moon-keep-already",
        {"city": "Almaty"},
        "🌙 Your moon city is already chosen: 📍 Almaty. You can change it in /moon.",
        "🌙 Город для лунных дней уже выбран: 📍 Almaty. Поменять можно в /moon.",
    ),
]


def _t(locale: Locale, key: str, **args: str | int) -> str:
    return " ".join(FluentTranslator().t(locale, key, **args).split())


def _sources(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    key = None
    for line in path.read_text().splitlines():
        start = re.match(r"([a-z][a-z0-9-]*) *=(.*)", line)
        if start:
            key = start[1]
            found[key] = start[2]
        elif key and line.startswith((" ", "\t")):
            found[key] += "\n" + line
        else:
            key = None
    return found


def _app(locale: str) -> dict[str, str]:
    return _sources(Path(str(APP_FTL).format(locale)))


def _new_copy(locale: str) -> dict[str, str]:
    every = _sources(Path(str(BOT_FTL).format(locale))) | _app(locale)
    return {k: v for k, v in every.items() if k in BOTH + BOT_ONLY}


@pytest.mark.parametrize("locale", LOCALES)
def test_every_new_bot_key_exists(locale: Locale) -> None:
    assert sorted(set(BOTH + BOT_ONLY) - message_ids(locale)) == []


@pytest.mark.parametrize("locale", LOCALES)
def test_the_shared_keys_are_in_the_mini_app_too(locale: str) -> None:
    assert sorted(set(BOTH) - set(_app(locale))) == []


@pytest.mark.parametrize("locale", LOCALES)
def test_the_mini_app_keys_read_as_the_bots(locale: str) -> None:
    bot = _sources(Path(str(BOT_FTL).format(locale)))
    app = _app(locale)
    for key in BOTH:
        if key == "moon-teacher-shared":  # /moon is a bot command: the app says "your own city"
            continue
        assert " ".join(app[key].split()) == " ".join(bot[key].split()), key


@pytest.mark.parametrize("locale", LOCALES)
def test_the_mini_app_never_points_to_a_bot_command(locale: str) -> None:
    app = _app(locale)
    assert all("/moon" not in app[key] for key in BOTH)


@pytest.mark.parametrize(
    ("key", "args", "en", "ru"), COPY, ids=[f"{r[0]}-{i}" for i, r in enumerate(COPY)]
)
def test_the_copy_reads_as_accepted(key: str, args: dict[str, str | int], en: str, ru: str) -> None:
    assert _t("en", key, **args) == en
    assert _t("ru", key, **args) == ru


def test_names_are_never_after_u_in_russian() -> None:
    for key, value in _new_copy("ru").items():
        assert not re.search(r"\bу\s*\{\s*\$name", value), key


def test_russian_copy_is_gender_neutral() -> None:
    for key, value in _new_copy("ru").items():
        assert "(а)" not in value, key
        assert not re.search(r"\bты\s+\w+л[аи]?\b", value, re.IGNORECASE), key


@pytest.mark.parametrize(
    ("locale", "words"),
    [
        ("en", ("should", "must", "forgot", "miss", "failed", "sorry", "guru")),
        ("ru", ("надо", "должен", "должна", "забы", "пропус", "гуру", "преподавател")),
    ],
)
def test_the_copy_stays_free_of_nudges(locale: str, words: tuple[str, ...]) -> None:
    for key, value in _new_copy(locale).items():
        for word in words:
            assert word not in value.lower(), (key, word)


def test_the_calc_note_still_says_follow_your_teacher() -> None:
    assert "follow your teacher" in _t("en", "moon-calc-note", city="Mysuru")
