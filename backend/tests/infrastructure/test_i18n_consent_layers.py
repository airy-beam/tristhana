# ruff: noqa: RUF001
"""ADR-0045: two layers, one consent. The full texts (`invite-consent`, `shala-join-consent`,
`shala-staff-consent`) are the consent record and are pinned byte for byte elsewhere; ✅ on the
short screen agrees to all of the full text (UI-06 Q312). This file keeps each short text in
step with its full text, so the two cannot drift apart:

- every bullet of a full text is listed below with what the short screen does with it, so a
  new or reworded bullet fails until someone decides where it goes;
- every data item the full text says the other side sees is named on the short screen;
- the short screen says nothing the full text does not say: apart from the one merged "sees"
  sentence of the teacher invite, each of its sentences is a sentence of the full text.

The short texts themselves are pinned byte for byte through the webhook, in
`tests/bots/test_teacher_links_bot.py` and `tests/bots/test_shalas_bot.py`.
"""

from dataclasses import dataclass
from typing import Literal

import pytest

from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

LOCALES: tuple[Locale, ...] = ("en", "ru")
ARGS = {"name": "Лена", "me": " (Ash)"}
BULLET = "• "

# What the short screen does with a bullet of the full text.
#   seen     data the other side sees: the short text names every item listed
#   kept     what stays private, and the way out: the short text names every item listed
#   details  what the other side can do, and the mechanics: only behind "Details"
type Layer = Literal["seen", "kept", "details"]


@dataclass(frozen=True)
class Bullet:
    starts: str  # how the full text's bullet begins
    layer: Layer
    items: tuple[str, ...] = ()  # each one is in this bullet, and on the short screen


@dataclass(frozen=True)
class Consent:
    full: str
    # The short text's first sentence may merge several "seen" bullets into one; every other
    # sentence must be in the full text word for word.
    merged_first: bool
    bullets: dict[Locale, tuple[Bullet, ...]]

    @property
    def short(self) -> str:
        return f"{self.full}-short"


INVITE = Consent(
    "invite-consent",
    merged_first=True,
    bullets={
        "en": (
            Bullet(
                "Лена sees your name",
                "seen",
                (
                    "your name (Ash)",
                    "from today on",
                    "practice or rest",
                    "how far your practice goes",
                ),
            ),
            Bullet("Лена also sees your last asana", "seen", ("your last asana",)),
            Bullet("All rest you log looks the same", "details"),
            Bullet(
                "If nothing shows for a while",
                "seen",
                ("If nothing shows for a while, Лена sees a short note saying just that.",),
            ),
            Bullet("Any teacher on your list can also mark a new asana", "details"),
            Bullet(
                "How you feel, your notes and the reason for a rest",
                "kept",
                ("How you feel", "your notes", "the reason for a rest", "stay private"),
            ),
            Bullet("Лена can send announcements", "details"),
            Bullet(
                "You can remove Лена from your list",
                "kept",
                ("any time", "☰ Menu → 🙏 Teacher and shala", "No one gets a message."),
            ),
        ),
        "ru": (
            Bullet(
                "Лена увидит твоё имя",
                "seen",
                ("твоё имя (Ash)", "с сегодняшнего дня", "практика или отдых", "объём практики"),
            ),
            Bullet("Ещё будет видна твоя последняя асана", "seen", ("последняя асана",)),
            Bullet("Любой отмеченный отдых выглядит одинаково", "details"),
            Bullet(
                "Если какое-то время показать нечего",
                "seen",
                ("Если какое-то время показать нечего, Лена увидит об этом короткую пометку.",),
            ),
            Bullet("Любой учитель из твоего списка может отметить", "details"),
            Bullet(
                "Самочувствие, заметки и причина отдыха",
                "kept",
                ("Самочувствие", "заметки", "причина отдыха", "остаются личными"),
            ),
            Bullet("Лена может отправлять объявления", "details"),
            Bullet(
                "Убрать из списка можно",
                "kept",
                ("в любой момент", "☰ Меню → 🙏 Учитель и шала", "Сообщений никто не получит."),
            ),
        ),
    },
)
JOIN = Consent(
    "shala-join-consent",
    merged_first=False,
    bullets={
        "en": (
            Bullet(
                "The shala's teachers and staff see your name",
                "seen",
                ("your name (Ash)", "Nothing from your log."),
            ),
            Bullet("The shala's staff can send announcements", "details"),
            Bullet("Your moon days follow the shala's calendar", "details"),
            Bullet(
                "The shala's staff can mark that you came to a class",
                "seen",
                ("mark that you came to a class", "can remove them any time"),
            ),
            Bullet(
                "You can leave any time",
                "kept",
                ("any time", "☰ Menu → 🙏 Teacher and shala", "No one gets a message."),
            ),
        ),
        "ru": (
            Bullet(
                "Преподаватели и команда шалы увидят твоё имя",
                "seen",
                ("твоё имя (Ash)", "Ничего из журнала."),
            ),
            Bullet("Команда шалы может отправлять участникам объявления", "details"),
            Bullet("Лунные дни будут считаться по календарю шалы", "details"),
            Bullet(
                "Посещение занятий может отмечать команда шалы",
                "seen",
                ("Посещение занятий может отмечать", "можно снять в любой момент"),
            ),
            Bullet(
                "Выйти можно в любой момент",
                "kept",
                ("в любой момент", "☰ Меню → 🙏 Учитель и шала", "Сообщений никто не получит."),
            ),
        ),
    },
)
STAFF = Consent(
    "shala-staff-consent",
    merged_first=False,
    bullets={
        "en": (
            Bullet(
                "Everyone in the shala, students included, sees your name",
                "seen",
                ("Everyone in the shala, students included", "your name (Ash)", "role"),
            ),
            Bullet(
                "You'll see the names of its students and staff",
                "seen",
                ("the names of its students and staff", "not their logs"),
            ),
            Bullet("The shala's announcements come to you", "details"),
            Bullet("You can mark who came to its classes", "details"),
            Bullet(
                "You can leave any time", "kept", ("any time", "☰ Menu → 🙏 Teacher and shala")
            ),
        ),
        "ru": (
            Bullet(
                "Все в шале, включая учеников, увидят твоё имя",
                "seen",
                ("Все в шале, включая учеников", "твоё имя (Ash)", "роль"),
            ),
            Bullet(
                "Тебе будут видны имена учеников и людей из команды",
                "seen",
                ("имена учеников и людей из команды", "но не их журналы"),
            ),
            Bullet("Объявления шалы тоже будут приходить тебе", "details"),
            Bullet("Можно отмечать посещение занятий", "details"),
            Bullet(
                "Выйти можно в любой момент",
                "kept",
                ("в любой момент", "☰ Меню → 🙏 Учитель и шала"),
            ),
        ),
    },
)
CONSENTS = (INVITE, JOIN, STAFF)
CASES = [(consent, locale) for consent in CONSENTS for locale in LOCALES]
IDS = [f"{consent.full}-{locale}" for consent, locale in CASES]


def _text(locale: Locale, key: str) -> str:
    return FluentTranslator().t(locale, key, **ARGS)


def _bullets(text: str) -> list[str]:
    return [line.removeprefix(BULLET) for line in text.splitlines() if line.startswith(BULLET)]


def _sentences(text: str) -> list[str]:
    """ "A. B." → ["A.", "B."]; none of these texts has a dot inside a sentence."""
    return [f"{part.strip().removesuffix('.')}." for part in text.split(". ") if part.strip()]


@pytest.mark.parametrize("locale", LOCALES)
def test_both_layers_exist_in_both_languages(locale: Locale) -> None:
    keys = message_ids(locale)

    for consent in CONSENTS:
        assert {consent.full, consent.short} <= keys
    assert {"consent-details", "consent-short-back"} <= keys
    assert {"invite-know-them", "shala-know-them"} <= keys  # the fourth line (ADR-0030)


@pytest.mark.parametrize(("consent", "locale"), CASES, ids=IDS)
def test_every_bullet_of_the_full_text_is_accounted_for(consent: Consent, locale: Locale) -> None:
    """A bullet added to or reworded in a full text must be listed here first: is it data the
    other side sees (then the short screen must name it), or does it live in Details?"""
    full = _bullets(_text(locale, consent.full))
    listed = consent.bullets[locale]

    assert len(full) == len(listed), full
    for bullet, row in zip(full, listed, strict=True):
        assert bullet.startswith(row.starts), bullet
        for item in row.items:
            assert item in bullet, (row.starts, item)


@pytest.mark.parametrize(("consent", "locale"), CASES, ids=IDS)
def test_the_short_text_names_every_item_the_full_text_says_is_seen(
    consent: Consent, locale: Locale
) -> None:
    short = _text(locale, consent.short)

    for row in consent.bullets[locale]:
        if row.layer == "details":
            assert not row.items, row.starts  # nothing to carry over
            continue
        assert row.items, row.starts  # a seen or kept bullet names what it carries over
        for item in row.items:
            assert item in short, (row.starts, item)


@pytest.mark.parametrize("consent", CONSENTS, ids=[c.full for c in CONSENTS])
def test_the_same_bullets_are_seen_kept_and_detailed_in_both_languages(consent: Consent) -> None:
    layers = {locale: [row.layer for row in consent.bullets[locale]] for locale in LOCALES}

    assert layers["en"] == layers["ru"]


@pytest.mark.parametrize(("consent", "locale"), CASES, ids=IDS)
def test_the_short_text_says_nothing_the_full_text_does_not(
    consent: Consent, locale: Locale
) -> None:
    """Each sentence of the short text is a sentence of the full text, word for word. The one
    exception is the teacher invite's first sentence, which folds two "sees" bullets into
    one; the item table above pins that one."""
    full = _text(locale, consent.full)
    sentences = [s for bullet in _bullets(_text(locale, consent.short)) for s in _sentences(bullet)]
    merged = sentences[:1] if consent.merged_first else []

    for sentence in sentences[len(merged) :]:
        assert sentence in full, sentence
    for sentence in merged:
        assert sentence not in full  # else it needs no exception
        seen = [item for row in consent.bullets[locale][:2] for item in row.items]
        assert all(item in sentence for item in seen), sentence


@pytest.mark.parametrize(("consent", "locale"), CASES, ids=IDS)
def test_the_short_text_is_three_lines_and_nothing_else(consent: Consent, locale: Locale) -> None:
    short = _text(locale, consent.short)

    assert len(short.splitlines()) == 3
    assert len(_bullets(short)) == 3  # no heading: the ask line above it is the heading
    assert len(short) < len(_text(locale, consent.full))


@pytest.mark.parametrize("locale", LOCALES)
def test_the_quiet_note_rides_on_the_short_invite(locale: Locale) -> None:
    """ADR-0031: `quiet_note_agreed` is set by the confirm of a text that names the note. The
    short screen's ✅ is that confirm (Q312), so the short text must name it."""
    note = INVITE.bullets[locale][3]

    assert note.layer == "seen"
    assert note.items[0] in _text(locale, INVITE.short)
    assert note.items[0] in _text(locale, INVITE.full)
