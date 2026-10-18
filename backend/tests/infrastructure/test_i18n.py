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
