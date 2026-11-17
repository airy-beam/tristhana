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
