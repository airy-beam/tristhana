# ruff: noqa: RUF001
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
    assert not re.search(r"\(а\)|\(ла\)|\(ась\)", T.t("ru", KEY))


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

    assert not re.search(r"\(а\)|\(ла\)|\(ась\)|подтвердил|ответил", text)
    assert not re.search(r"\b[Вв]ы\b|\b[Вв]аш", text)


def test_no_answer_says_yet_and_offers_a_way_on() -> None:
    en, ru = (T.t(locale, "request-no-answer", name="Anna") for locale in ("en", "ru"))

    assert "yet" in en
    assert "пока" in ru


# The bot's screens (spec §2: the copy keys; §8: i18n)

STUDENT_KEYS = (
    "request-ask",
    "request-ask-one",
    "request-yes",
    "request-consent-short",
    "request-until-yes",
    "request-know-them",
    "request-consent",
    "request-asked",
    "request-waiting",
    "request-recent",
    "request-too-many",
    "request-full",
    "request-open",
    "request-nobody",
    "request-waiting-line",
    "request-withdraw",
    "request-withdraw-ask",
    "request-withdraw-yes",
    "request-withdrawn",
    "request-confirmed",
    "request-no-answer",
    "request-pick-another",
)
TEACHER_KEYS = (
    "request-note",
    "request-yes-mine",
    "request-not-mine",
    "request-see-all",
    "request-declined",
    "request-undo",
    "request-gone",
    "request-already-student",
    "request-list-full",
    "request-list-title",
    "request-list-hint",
    "request-list-empty",
    "request-all",
    "request-all-ask",
    "request-all-yes",
    "request-all-done",
    "request-waiting-open",
    "request-no-teachers-hint",
)
ARGS = {"name": "Анна", "me": " (Ash)", "student": "Ash", "shala": "Ashtanga Almaty", "count": 3}
LOCALES = ("en", "ru")


def _text(locale: str, key: str, **args: str | int) -> str:
    return T.t(locale, key, **(ARGS | args))  # type: ignore[arg-type]


@pytest.mark.parametrize("locale", LOCALES)
def test_every_request_key_exists_in_both_languages_and_no_other(locale: str) -> None:
    from tristhana.infrastructure.i18n.fluent import message_ids

    listed = {*STUDENT_KEYS, *TEACHER_KEYS}

    assert {key for key in message_ids(locale) if key.startswith("request-")} == listed  # type: ignore[arg-type]
    for key in listed:
        assert _text(locale, key) != key


@pytest.mark.parametrize("key", STUDENT_KEYS)
@pytest.mark.parametrize("locale", LOCALES)
def test_nothing_the_student_reads_has_a_word_for_a_refusal(locale: str, key: str) -> None:
    text = _text(locale, key).lower()

    assert not re.search("отклон|отказ|declin|reject|refus|denied|turned down", text)


@pytest.mark.parametrize("key", [*STUDENT_KEYS, *TEACHER_KEYS])
def test_russian_is_informal_with_no_gendered_ending(key: str) -> None:
    text = _text("ru", key)

    assert not re.search(r"\(а\)|\(ла\)|\(ась\)|подтвердил|ответил|выбрал|отправил|отозвал", text)
    assert not re.search(r"\b[Вв]ы\b|\b[Вв]аш|\b[Вв]ам\b|\b[Вв]ас\b", text)


def test_russian_keeps_teacher_and_the_shala_role_apart() -> None:
    """SC-01 glossary: «учитель» is the person asked; «Преподаватель» only names the role."""
    for key in (*STUDENT_KEYS, *TEACHER_KEYS):
        text = _text("ru", key)
        if key == "request-no-teachers-hint":
            assert "«Преподаватель»" in text
        else:
            assert "реподавател" not in text, key


NAMED = (
    "request-ask-one",
    "request-asked",
    "request-waiting",
    "request-recent",
    "request-waiting-line",
    "request-withdraw",
    "request-withdraw-ask",
    "request-confirmed",
    "request-no-answer",
    "request-declined",
)


@pytest.mark.parametrize("key", NAMED)
@pytest.mark.parametrize("locale", LOCALES)
def test_a_name_is_shown_as_given(locale: str, key: str) -> None:
    assert "Анна" in _text(locale, key)  # nominative: a name is never declined


@pytest.mark.parametrize("locale", LOCALES)
def test_the_teachers_note_names_the_student_and_the_shala(locale: str) -> None:
    text = _text(locale, "request-note")

    assert "Ash" in text
    assert "Ashtanga Almaty" in text
    assert re.search("only if you know|только если знаешь", text)


@pytest.mark.parametrize(
    ("locale", "n", "word"),
    [
        ("en", 1, "1 person is"),
        ("en", 2, "2 people are"),
        ("ru", 1, "1 человек ждёт"),
        ("ru", 3, "3 человека ждут"),
        ("ru", 5, "5 человек ждут"),
        ("ru", 21, "21 человек ждёт"),
    ],
)
def test_the_waiting_list_title_is_a_fluent_plural(locale: str, n: int, word: str) -> None:
    assert word in T.t(locale, "request-list-title", count=n)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("locale", "n", "word"),
    [
        ("en", 1, "1 student is"),
        ("en", 4, "4 students are"),
        ("ru", 1, "1 ученик теперь"),
        ("ru", 2, "2 ученика теперь"),
        ("ru", 5, "5 учеников теперь"),
        ("ru", 21, "21 ученик теперь"),
    ],
)
def test_confirm_all_says_how_many_as_a_fluent_plural(locale: str, n: int, word: str) -> None:
    assert word in T.t(locale, "request-all-done", count=n)  # type: ignore[arg-type]
    assert str(n) in T.t(locale, "request-all-ask", count=n)  # type: ignore[arg-type]
    assert str(n) in T.t(locale, "request-all", count=n)  # type: ignore[arg-type]


# One consent, two layers (ADR-0045), with the items of the personal link's (ADR-0046)

BULLET = "• "
# What `invite-consent` says the teacher sees, what stays private, and the way out: each is
# in both layers of the request consent, in "the teacher you pick" wording.
ITEMS: dict[str, tuple[str, ...]] = {
    "en": (
        "your name (Ash)",
        "from today on",
        "practice or rest",
        "your practice length",
        "your last asana",
        "If nothing shows for a while",
        "a short note saying just that",
        "Check-ins",
        "diary notes",
        "the reason for a rest",
        "stay private",
        "any time in /teachers",
        "No one gets a message.",
    ),
    "ru": (
        "твоё имя (Ash)",
        "с сегодняшнего дня",
        "практика или отдых",
        "объём практики",
        "последняя асана",
        "Если какое-то время показать нечего",
        "короткую пометку",
        "Самочувствие",
        "заметки",
        "причина отдыха",
        "остаются личными",
        "в любой момент в /teachers",
        "Сообщений никто не получит.",
    ),
}
# Only behind "Details", as on the personal link: what the teacher can do, and the mechanics.
DETAILS: dict[str, tuple[str, ...]] = {
    "en": ("All rest you log looks the same", "mark a new asana", "send announcements"),
    "ru": ("Любой отмеченный отдых выглядит одинаково", "отметить тебе новую асану", "объявления"),
}


def _bullets(text: str) -> list[str]:
    return [line.removeprefix(BULLET) for line in text.splitlines() if line.startswith(BULLET)]


def _sentences(text: str) -> list[str]:
    return [f"{part.strip().removesuffix('.')}." for part in text.split(". ") if part.strip()]


@pytest.mark.parametrize("locale", LOCALES)
def test_the_request_consent_names_the_same_items_as_the_invite_consent(locale: str) -> None:
    invite = _text(locale, "invite-consent")
    full = _text(locale, "request-consent")
    short = _text(locale, "request-consent-short")

    for item in ITEMS[locale]:
        assert item in invite, item  # the table follows the personal link's consent
        assert item in full, item
        assert item in short, item
    for item in DETAILS[locale]:
        assert item in invite, item
        assert item in full, item
        assert item not in short, item


@pytest.mark.parametrize("locale", LOCALES)
def test_the_request_consent_is_the_invite_consent_plus_three_request_lines(locale: str) -> None:
    """Spec §3: nothing is visible until they confirm; counted from today even if they
    confirm some days later; withdraw before, remove after."""
    invite = _bullets(_text(locale, "invite-consent"))
    full = _bullets(_text(locale, "request-consent"))

    assert len(full) == len(invite) + 3
    until, today, withdraw = full[-3:]
    assert until == _text(locale, "request-until-yes")  # the short screen's own line
    assert re.search("from today|с сегодняшнего", today)
    assert re.search("withdraw|отозвать", withdraw)
    assert "Анна" not in _text(locale, "request-consent")  # no name: "the teacher you pick"


@pytest.mark.parametrize("locale", LOCALES)
def test_the_short_request_consent_says_nothing_the_full_text_does_not(locale: str) -> None:
    """As ADR-0045's other pairs: three lines, and apart from the merged "sees" sentence each
    sentence of the short screen is a sentence of the full text, word for word."""
    full = _text(locale, "request-consent")
    short = _text(locale, "request-consent-short")
    sentences = [s for bullet in _bullets(short) for s in _sentences(bullet)]

    assert len(short.splitlines()) == len(_bullets(short)) == 3
    assert sentences[0] not in full  # the merged one, pinned by the item table above
    for sentence in sentences[1:]:
        assert sentence in full, sentence
    for sentence in _sentences(_text(locale, "request-until-yes")):
        assert sentence in full, sentence
    assert len(short) < len(full)


@pytest.mark.parametrize("locale", LOCALES)
def test_both_layers_name_the_quiet_note_the_tap_agrees_to(locale: str) -> None:
    """ADR-0031: `h1:ta` stores `quiet_note_agreed`, so every screen that carries it must
    name the note."""
    from tristhana.bots.telegram.teacher_requests import QUIET_NOTE_AGREED

    note = ITEMS[locale][5]

    assert QUIET_NOTE_AGREED is True
    assert note in _text(locale, "request-consent")
    assert note in _text(locale, "request-consent-short")


def test_the_personal_link_and_join_consents_are_unchanged_on_purpose() -> None:
    """Spec §2: joining alone still shares nothing, so `shala-join-consent` says nothing
    about a teacher's view; the question comes after it, with its own consent."""
    for locale in LOCALES:
        join = _text(locale, "shala-join-consent")
        assert not re.search("last asana|последняя асана|practice length|объём практики", join)


@pytest.mark.parametrize("locale", LOCALES)
def test_gone_is_one_line_with_the_way_out(locale: str) -> None:
    text = _text(locale, "request-gone")

    assert re.search("your own link|свою ссылку", text)
    assert "Анна" not in text
    assert not re.search("expired|withdr|left|истёк|отозв|вышел|удал", text.lower())


@pytest.mark.parametrize("locale", LOCALES)
def test_the_teacher_is_told_the_student_isnt_told(locale: str) -> None:
    for key in ("request-declined", "request-list-hint"):
        assert re.search("isn't told|не узнает", _text(locale, key)), key
