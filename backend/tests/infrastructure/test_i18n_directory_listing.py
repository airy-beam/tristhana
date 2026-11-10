"""ID-05 copy rules (spec §1, §2, §10, §12a; ADR-0042), on the bot's Fluent files.

The line states one checked fact and names Sharath Yoga Centre in full; it never says badge,
verified, official or endorsed (except the one "not an endorsement" sentence); the decline
never claims the name is absent from the directory; the level is the teacher's own words;
the month stands alone after the colon (nominative in Russian); Russian stays gender-neutral.
Exact wording is the ux-writer's, so only the rules are pinned here."""

import re
from datetime import date

import pytest

from tristhana.application.ports.i18n import DateArg
from tristhana.domain.directory_listing import DeclaredLevel
from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

T = FluentTranslator()
WHEN = DateArg(date(2026, 11, 11), style="month")
ARGS: dict[str, str | int | DateArg] = {
    "listed": "Anna Petrova",
    "when": WHEN,
    "level": "certified",
    "waiting": 2,
    "name": "Anna",
    "region": "Russia",
    "note": "a note",
    "date": DateArg(date(2026, 11, 11), with_year=True),
}
AVOID = {
    "en": ("badge", "verified", "unverified", "certified by", "approved", "official", "guru"),
    "ru": ("значок", "значк", "подтвержд", "официальн", "одобрен", "гуру"),  # noqa: RUF001
}


def _keys(locale: Locale) -> list[str]:
    found = sorted(k for k in message_ids(locale) if k.startswith(("listing-", "admin-listing-")))
    return [*found, "export-readme-listing"]


def _text(locale: Locale, key: str) -> str:
    return T.t(locale, key, **ARGS)


def test_the_keys_are_in_parity() -> None:
    assert _keys("en") == _keys("ru")
    assert len(_keys("en")) >= 40


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_every_key_renders(locale: Locale) -> None:
    for key in _keys(locale):
        assert _text(locale, key).strip()


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_the_copy_avoids_the_words_that_imply_endorsement(locale: Locale) -> None:
    for key in _keys(locale):
        text = _text(locale, key).lower()
        for word in AVOID[locale]:
            assert word not in text, (key, word)
        if key != "listing-about":  # the one sentence that says it is NOT an endorsement
            assert "endorse" not in text, key
            assert "рекомендац" not in text, key


def test_the_about_text_says_what_the_line_is_not() -> None:
    en, ru = _text("en", "listing-about"), _text("ru", "listing-about")
    assert "not an endorsement" in en
    assert "Many experienced teachers are not in this directory" in en
    assert "не рекомендация" in ru
    assert "Многих опытных учителей в этом списке нет" in ru


@pytest.mark.parametrize(
    ("locale", "line"),
    [
        (
            "en",
            "✔ Listed in the Sharath Yoga Centre teachers directory as Anna Petrova"
            " (checked: November 2026)",
        ),
        ("ru", "✔ Anna Petrova — в списке учителей Sharath Yoga Centre (сверено: ноябрь 2026)"),
    ],
)
def test_the_line(locale: Locale, line: str) -> None:
    assert _text(locale, "listing-mark") == line
    assert "\n" not in line


@pytest.mark.parametrize(
    ("month", "en", "ru"),
    [
        (3, "March 2026", "март 2026"),
        (5, "May 2026", "май 2026"),
        (8, "August 2026", "август 2026"),
    ],
)
def test_the_month_stands_alone(month: int, en: str, ru: str) -> None:
    when = DateArg(date(2026, month, 31 if month != 8 else 1), style="month")
    assert T.t("en", "admin-listing-oldest", when=when).endswith(en)
    assert T.t("ru", "admin-listing-oldest", when=when).endswith(ru)  # nominative, no year suffix


@pytest.mark.parametrize("level", list(DeclaredLevel))
def test_every_level_has_a_name_and_russian_keeps_the_english_title(
    level: DeclaredLevel,
) -> None:
    en = T.t("en", "listing-level-name", level=level.value)
    ru = T.t("ru", "listing-level-name", level=level.value)
    assert en in ("Authorised", "Authorised Level 1", "Authorised Level 2", "Certified")
    assert ru.startswith(en + " (")
    assert "✔" not in T.t("en", "listing-level", level=en)  # the level is never ticked


@pytest.mark.parametrize("key", ["listing-not-found", "listing-note-not-found"])
def test_a_decline_never_claims_the_name_is_absent(key: str) -> None:
    en, ru = _text("en", key), _text("ru", key)
    assert "couldn't confirm" in en
    assert "couldn't find" not in en
    assert "не получилось" in ru
    assert "нет в списке" not in ru


def test_the_ended_note_is_gentle_and_only_about_the_directory() -> None:
    en = _text("en", "listing-note-ended")
    assert "says nothing about your teaching" in en
    assert "Everything else stays as it is" in en


def test_the_admins_note_carries_no_name() -> None:
    for locale in ("en", "ru"):
        text = T.t(locale, "admin-listing-new")  # no arguments at all
        assert "/admin" in text


def test_russian_copy_is_gender_neutral_and_informal() -> None:
    gendered = re.compile(r"\b\w+(л|лась|лся)\(а\)|\(а\)|\bВы\b|\bВаш")  # noqa: RUF001
    for key in _keys("ru"):
        assert not gendered.search(_text("ru", key)), key
