# ruff: noqa: RUF001
"""SC-06 copy (spec §2 table, §7; expert item 1): the feed keys in `bot.ftl` and the Mini App
keys in `app.ftl`, both languages, `feed-` keys in parity; the drafted rows (⚑ the ux-writer
pass may change the wording: update this table with it); `ics-class` joins the title or type
with the teacher; the moon description is the existing `moon-calc-note`, word for word, with
no new moon wording."""

import re
from pathlib import Path

import pytest

from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

ROOT = Path(__file__).resolve().parents[3]
LOCALES: tuple[Locale, ...] = ("en", "ru")
SCREEN_KEYS = (
    "feed-open",
    "feed-title",
    "feed-explain",
    "feed-moon-only",
    "feed-create",
    "feed-google",
    "feed-google-phone",
    "feed-apple",
    "feed-private",
    "feed-checked",
    "feed-rotate",
    "feed-rotate-confirm",
    "feed-off",
    "feed-off-confirm",
    "feed-off-done",
)
BOT_KEYS = (*SCREEN_KEYS, "feed-copy", "ics-calendar-name", "ics-class")
APP_KEYS = (*SCREEN_KEYS, "feed-copy", "feed-copied")
COPY: list[tuple[str, dict[str, str], str, str]] = [
    ("feed-open", {}, "📅 Add to calendar", "📅 Добавить в календарь"),
    ("feed-title", {}, "📅 Calendar subscription", "📅 Подписка в календаре"),
    (
        "feed-explain",
        {},
        "Your classes and moon days in Google, Apple or Outlook Calendar. It updates by itself"
        " (Google can take up to a day).",
        "Твои занятия и лунные дни в Google, Apple или Outlook Календаре. Обновляется само"
        " (в Google — до суток).",
    ),
    (
        "feed-moon-only",
        {},
        "Join a shala to see its classes here too.",
        "Когда вступишь в шалу, здесь появятся и её занятия.",
    ),
    ("feed-create", {}, "📅 Create my link", "📅 Создать ссылку"),
    ("feed-google", {}, "Add to Google Calendar", "Добавить в Google Календарь"),
    ("feed-apple", {}, "Add to Apple / Outlook", "Добавить в Apple / Outlook"),
    (
        "feed-google-phone",
        {},
        "On a phone the Google button may not add it. Do it once on a computer: calendar.google.com"
        " → Other calendars + → From URL, and paste the link. Then it shows on your phone too.",
        "С телефона кнопка Google может не сработать. Сделай это один раз на компьютере:"
        " calendar.google.com → «Другие календари» + → по URL, и вставь ссылку. После этого"
        " календарь появится и на телефоне.",
    ),
    (
        "feed-private",
        {},
        "🔒 Anyone with this link sees your schedule. Don't share it; if it got out, make a new"
        " one.",
        "🔒 По этой ссылке видно твоё расписание. Не пересылай её; если она попала к кому-то,"
        " создай новую.",
    ),
    ("feed-checked", {"day": "none"}, "Not used by a calendar yet", "Календарь ещё не подключён"),
    (
        "feed-checked",
        {"day": "Sat 7 Nov"},
        "Last checked by a calendar: Sat 7 Nov",
        "Календарь последний раз обновлялся: Sat 7 Nov",
    ),
    ("feed-rotate", {}, "🔄 New link", "🔄 Новая ссылка"),
    (
        "feed-rotate-confirm",
        {},
        "The old link stops working. Calendars that use it need the new one.",
        "Старая ссылка перестанет работать. В календаре нужно будет подписаться заново.",
    ),
    ("feed-off", {}, "Turn off", "Отключить"),
    ("feed-off-done", {}, "Turned off.", "Отключено."),
    ("ics-calendar-name", {}, "Tristhana: my schedule", "Tristhana: моё расписание"),
    ("ics-class", {"what": "Mysore", "teacher": "Anna"}, "Mysore · Anna", "Mysore · Anna"),
]
MOON_CALC_NOTE = {
    "en": "Dates are calculated for 📍 Mysuru (lunar day at sunrise). Your shala's calendar may"
    " differ by a day; follow your teacher.",
    "ru": "Даты рассчитаны по городу 📍 Mysuru (лунный день на восходе). Календарь твоей шалы"
    " может отличаться на день: ориентируйся на своего учителя.",
}


def _flat(text: str) -> str:
    return " ".join(text.replace("⁨", "").replace("⁩", "").split())


def _app_ids(locale: Locale) -> set[str]:
    text = (ROOT / "miniapp" / "src" / "locales" / locale / "app.ftl").read_text()
    return set(re.findall(r"^([a-z][a-z0-9-]*)\s*=", text, flags=re.MULTILINE))


@pytest.mark.parametrize("locale", LOCALES)
def test_every_bot_key_exists(locale: Locale) -> None:
    assert set(BOT_KEYS) - message_ids(locale) == set()


@pytest.mark.parametrize("locale", LOCALES)
def test_every_mini_app_key_exists(locale: Locale) -> None:
    assert set(APP_KEYS) - _app_ids(locale) == set()


def test_the_bot_feed_keys_are_in_parity() -> None:
    prefixes = ("feed-", "ics-")
    en = {i for i in message_ids("en") if i.startswith(prefixes)}
    ru = {i for i in message_ids("ru") if i.startswith(prefixes)}

    assert en == ru


def test_the_mini_app_feed_keys_are_in_parity() -> None:
    en = {i for i in _app_ids("en") if i.startswith("feed-")}
    ru = {i for i in _app_ids("ru") if i.startswith("feed-")}

    assert en == ru


@pytest.mark.parametrize(("key", "args", "en", "ru"), COPY)
def test_the_drafted_rows(key: str, args: dict[str, str], en: str, ru: str) -> None:
    t = FluentTranslator()

    assert (_flat(t.t("en", key, **args)), _flat(t.t("ru", key, **args))) == (en, ru)


def test_the_off_confirm_says_calendars_keep_the_last_copy() -> None:
    t = FluentTranslator()

    assert _flat(t.t("en", "feed-off-confirm")).startswith("Your calendar apps will stop updating.")
    assert _flat(t.t("ru", "feed-off-confirm")).startswith("Календарь перестанет обновляться")


@pytest.mark.parametrize("locale", LOCALES)
def test_the_moon_description_is_the_calc_note_unchanged(locale: Locale) -> None:
    """Expert item 1: the feed reuses this text, so it is pinned here word for word."""
    assert FluentTranslator().t(locale, "moon-calc-note", city="Mysuru") == MOON_CALC_NOTE[locale]


@pytest.mark.parametrize("locale", LOCALES)
def test_no_new_moon_wording(locale: Locale) -> None:
    """The draft «Лунный день для 📍…» was dropped: no `ics-` key carries moon words."""
    from fluent.syntax import FluentParser, FluentSerializer, ast

    folder = ROOT / "backend" / "src" / "tristhana" / "infrastructure" / "i18n" / "locales"
    seen = 0
    for path in sorted((folder / locale).glob("*.ftl")):
        for entry in FluentParser().parse(path.read_text(encoding="utf-8")).body:
            if isinstance(entry, ast.Message) and entry.id.name.startswith("ics-"):
                seen += 1
                text = FluentSerializer().serialize_entry(entry)
                assert "📍" not in text, entry.id.name
                assert "Лунный день" not in text, entry.id.name
                assert "kshaya" not in text.lower(), entry.id.name
    assert seen >= 2  # ics-calendar-name, ics-class


def test_the_moon_summaries_are_the_long_phase_names() -> None:
    t = FluentTranslator()

    assert t.t("en", "moon-phase-long", phase="purnima") == "🌕 Full moon (Purnima)"
    assert t.t("en", "moon-phase-long", phase="amavasya") == "🌑 New moon (Amavasya)"
    assert t.t("ru", "moon-phase-long", phase="purnima") == "🌕 Полнолуние (Пурнима)"
    assert t.t("ru", "moon-phase-long", phase="amavasya") == "🌑 Новолуние (Амавасья)"
