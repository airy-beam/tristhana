from importlib.resources import files

import pytest

from tristhana.domain.locale import LOCALES
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

BOT_KEYS = ["start-greeting", "help-text", "fallback-text"]


def test_every_locale_has_the_same_keys() -> None:
    keys = {locale: message_ids(locale) for locale in LOCALES}

    assert keys["en"] == keys["ru"]
    assert set(BOT_KEYS) <= keys["en"]


def test_ftl_files_ship_as_package_data() -> None:
    root = files("tristhana.infrastructure.i18n") / "locales"
    for locale in LOCALES:
        assert (root / locale / "bot.ftl").is_file()


@pytest.mark.parametrize(("locale", "word"), [("en", "Namaste 🙏"), ("ru", "Намасте 🙏")])
def test_greeting_renders(locale: str, word: str) -> None:
    text = FluentTranslator().t(locale, "start-greeting")  # type: ignore[arg-type]

    assert text.startswith(word)
    assert "{" not in text


def test_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        FluentTranslator().t("en", "no-such-key")


def test_dates_are_localized_and_the_caller_decides_the_year() -> None:
    from datetime import date

    from tristhana.application.ports.i18n import DateArg

    t = FluentTranslator()
    day = date(2026, 10, 18)

    assert t.t("en", "day-label", rel="other", date=DateArg(day)) == "Sun, Oct 18"
    assert t.t("ru", "day-label", rel="today", date=DateArg(day)) == "Сегодня, вс, 18 окт."
    assert "2026" in t.t("en", "day-label", rel="other", date=DateArg(day, with_year=True))


@pytest.mark.parametrize(
    ("day", "at", "zone", "locale", "label"),
    [
        ("2026-10-19", "06:30", "Asia/Almaty", "en", "06:30 Almaty (UTC+5)"),
        ("2026-10-19", "06:30", "Asia/Almaty", "ru", "06:30 Алматы (UTC+5)"),
        ("2026-10-19", "04:30", "Asia/Kolkata", "en", "04:30 Kolkata (UTC+5:30)"),
        ("2026-10-19", "05:00", "Asia/Kathmandu", "en", "05:00 Kathmandu (UTC+5:45)"),
        ("2026-03-28", "06:30", "Europe/Berlin", "en", "06:30 Berlin (UTC+1)"),  # before DST
        ("2026-03-29", "06:30", "Europe/Berlin", "en", "06:30 Berlin (UTC+2)"),  # DST day
        ("2026-10-19", "06:30", "UTC", "en", "06:30 UTC"),
    ],
)
def test_time_labels_carry_city_and_the_offset_on_that_date(
    day: str, at: str, zone: str, locale: str, label: str
) -> None:
    from datetime import date, time

    from tristhana.application.ports.i18n import TimeArg

    arg = TimeArg(date.fromisoformat(day), time.fromisoformat(at), zone)

    assert FluentTranslator().t(locale, "time-label", time=arg) == label  # type: ignore[arg-type]


# WH-01 part 2 (spec §7): new keys exist in both locales and format as written.

WH01_KEYS = [
    "pause-ask",
    "pause-days",
    "pause-other",
    "pause-back",
    "pause-set",
    "log-auto-period",
    "pause-end",
    "pause-ended",
    "pause-cut",
    "pause-keep",
    "pause-kept",
    "remind-paused-until",
    "remind-resume",
    "settings-ladies-line",
    "settings-ladies-hide",
    "settings-ladies-show",
]
RU_ASK_ON = (
    "⏸ На сколько дней приостановить напоминания о практике, включая сегодня? "  # noqa: RUF001
    "Эти дни отметятся как „🌸 Женские дни“, если не отметишь иначе."
)
RU_ASK_OFF = "Сколько дней отметить как „🌸 Женские дни“, включая вчерашний день?"
RU_PAUSED = "⏸ На паузе по чт, 29 окт. включительно"  # noqa: RUF001
EN_ASK_ON = (
    "⏸ Pause practice reminders for how many days, including today? Those days show "
    "as 🌸 Ladies' holiday unless you log something else."
)
EN_ASK_OFF = "How many days should show as 🌸 Ladies' holiday, including yesterday?"


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_wh01_keys_exist(locale: str) -> None:
    assert set(WH01_KEYS) <= message_ids(locale)  # type: ignore[arg-type]


def _t(locale: str, key: str, **args: object) -> str:
    return FluentTranslator().t(locale, key, **args)  # type: ignore[arg-type]


def _flat(locale: str, key: str, **args: object) -> str:
    return " ".join(_t(locale, key, **args).split())


def _label(locale: str, status: str) -> str:
    return _t(locale, f"status-{status}")


def _until() -> object:
    from datetime import date

    from tristhana.application.ports.i18n import DateArg

    return DateArg(date(2026, 10, 29))  # a Thursday


@pytest.mark.parametrize(
    ("locale", "reminders", "rel", "expected"),
    [
        ("en", "on", "today", EN_ASK_ON),
        ("en", "off", "yesterday", EN_ASK_OFF),
        ("ru", "on", "today", RU_ASK_ON),
        ("ru", "off", "yesterday", RU_ASK_OFF),
    ],
)
def test_pause_ask(locale: str, reminders: str, rel: str, expected: str) -> None:
    label = _label(locale, "ladies")
    assert _flat(locale, "pause-ask", label=label, rel=rel, reminders=reminders) == expected


@pytest.mark.parametrize(
    ("locale", "n", "expected"),
    [
        ("en", 2, "2 days"),
        ("en", 14, "14 days"),
        ("ru", 2, "2 дня"),
        ("ru", 3, "3 дня"),
        ("ru", 4, "4 дня"),
        ("ru", 5, "5 дней"),
        ("ru", 6, "6 дней"),
        ("ru", 7, "7 дней"),
        ("ru", 10, "10 дней"),
        ("ru", 14, "14 дней"),
    ],
)
def test_pause_days_plurals(locale: str, n: int, expected: str) -> None:
    assert _t(locale, "pause-days", n=n) == expected


@pytest.mark.parametrize(
    ("locale", "reminders", "expected"),
    [
        ("en", "on", "⏹ End the pause"),
        ("en", "off", "⏹ End early"),
        ("ru", "on", "⏹ Завершить паузу"),
        ("ru", "off", "⏹ Закончить раньше"),
    ],
)
def test_pause_end_label_follows_the_reminders(locale: str, reminders: str, expected: str) -> None:
    assert _t(locale, "pause-end", reminders=reminders) == expected


def test_pause_set_and_ended_have_reminders_off_variants() -> None:
    label = _label("en", "sick")
    assert _flat("en", "pause-set", label=label, until=_until(), reminders="on") == (
        "⏸ Practice reminders are paused through Thu, Oct 29. Those days show as "
        "🤒 Sick / injury; you can log any day differently."
    )
    assert _flat("en", "pause-set", label=label, until=_until(), reminders="off") == (
        "⏸ Set through Thu, Oct 29. Those days show as 🤒 Sick / injury; you can log any day "
        "differently."
    )
    assert _t("en", "pause-ended", label=label, reminders="on") == (
        "▶️ Practice reminders are back from today."
    )
    assert _t("en", "pause-ended", label=label, reminders="off") == (
        "⏹ Done: from today on, days no longer show as 🤒 Sick / injury."
    )


def test_pause_cut_and_kept_name_the_period_gently() -> None:
    en, ru = _label("en", "sick"), _label("ru", "sick")
    assert _flat("en", "pause-cut", label=en, until=_until(), rel="today") == (
        "⏸ Practice logged for today, so the following days, through Thu, Oct 29, "
        "no longer show as 🤒 Sick / injury. Keep them as they were?"
    )
    assert "yesterday" in _t("en", "pause-cut", label=en, until=_until(), rel="yesterday")
    assert "на вчера" in _t("ru", "pause-cut", label=ru, until=_until(), rel="yesterday")
    assert _t("en", "pause-kept", label=en, until=_until()) == (
        "⏸ Pause kept: 🤒 Sick / injury through Thu, Oct 29."
    )
    assert _t("ru", "pause-kept", label=ru, until=_until()) == (
        "⏸ Пауза сохранена: „🤒 Болезнь / травма“ по чт, 29 окт. включительно."
    )
    for locale, label in (("en", en), ("ru", ru)):
        text = _t(locale, "pause-cut", label=label, until=_until(), rel="today").lower()
        assert "missed" not in text
        assert "пропущ" not in text


def test_period_line_paused_line_and_settings_line() -> None:
    travel = _label("en", "travel")
    assert _flat("en", "log-auto-period", label=travel, until=_until()) == (
        "✈️ Travel through Thu, Oct 29. If the day went differently, log it below."
    )
    assert _t("ru", "remind-paused-until", until=_until()) == RU_PAUSED
    assert _t("en", "remind-resume") == "▶️ Resume now"
    assert _t("ru", "settings-ladies-line", shown="yes") == "🌸 Кнопка „Женские дни“: показана"
    assert _t("en", "settings-ladies-line", shown="no") == "🌸 Ladies' holiday button: hidden"
    assert (_t("en", "settings-ladies-hide"), _t("en", "settings-ladies-show")) == (
        "🌸 Hide the button",
        "🌸 Show the button",
    )
