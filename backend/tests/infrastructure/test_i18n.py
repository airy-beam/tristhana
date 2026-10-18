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
