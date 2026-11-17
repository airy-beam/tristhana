"""ID-07 copy that ships with the core (spec §2, §6): the export README paragraph, in both
languages. The bot's and the app's keys come with their screens."""

import re

import pytest

from tristhana.application.export import README_KEYS
from tristhana.domain.teacher_requests import RequestState, exported_state
from tristhana.infrastructure.i18n.fluent import FluentTranslator

KEY = "export-readme-requests"
T = FluentTranslator()


def test_the_paragraph_is_part_of_the_readme_after_the_links() -> None:
    assert README_KEYS.index(KEY) == README_KEYS.index("export-readme-links") + 1


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_it_names_the_list_and_every_word_the_export_can_hold(locale: str) -> None:
    from datetime import UTC, datetime, timedelta

    text = T.t(locale, KEY)  # type: ignore[arg-type]
    asked = datetime(2026, 11, 17, tzinfo=UTC)
    words = {
        exported_state(mine, state, asked, asked + timedelta(days=days))
        for mine in (True, False)
        for state in RequestState
        for days in (0, 8)
    }

    assert text != KEY
    assert "teacher_requests" in text
    assert "30" in text
    assert "7" in text
    for word in (*words, "other_side", "teacher", "student"):
        assert word in text, (locale, word)


def test_russian_has_no_word_for_a_refusal_beyond_the_machine_name() -> None:
    """The student never reads that a teacher said no (spec §2): the one place the word can
    stand is the code a teacher's own export holds."""
    text = T.t("ru", KEY).lower()

    assert not re.search("отклон|отказ", text)
    assert text.count("declined") == 1
    assert "rejected" not in text


def test_russian_has_no_gendered_ending() -> None:
    assert not re.search(r"\(а\)|\(ла\)|\(ась\)", T.t("ru", KEY))  # noqa: RUF001


# The student's two closing notes (the tick sends them; spec §2, §8)

CLOSING_KEYS = ("request-confirmed", "request-no-answer")


@pytest.mark.parametrize("key", CLOSING_KEYS)
@pytest.mark.parametrize("locale", ["en", "ru"])
def test_a_closing_note_names_the_teacher_in_both_languages(locale: str, key: str) -> None:
    text = T.t(locale, key, name="Анна")  # type: ignore[arg-type]

    assert text != key
    assert "Анна" in text  # nominative, as given: a name is never declined


@pytest.mark.parametrize("key", CLOSING_KEYS)
@pytest.mark.parametrize("locale", ["en", "ru"])
def test_a_closing_note_has_no_word_for_a_refusal(locale: str, key: str) -> None:
    text = T.t(locale, key, name="Anna").lower()  # type: ignore[arg-type]

    assert not re.search("отклон|отказ|declin|reject|refus", text)


@pytest.mark.parametrize("key", CLOSING_KEYS)
def test_a_russian_closing_note_is_informal_and_has_no_gendered_ending(key: str) -> None:
    text = T.t("ru", key, name="Анна")

    assert not re.search(r"\(а\)|\(ла\)|\(ась\)|подтвердил|ответил", text)  # noqa: RUF001
    assert not re.search(r"\b[Вв]ы\b|\b[Вв]аш", text)


def test_no_answer_says_yet_and_offers_a_way_on() -> None:
    en, ru = (T.t(locale, "request-no-answer", name="Anna") for locale in ("en", "ru"))

    assert "yet" in en
    assert "пока" in ru
