"""Teacher requests in the bot, the messages the bot sends on its own (ID-07 spec §2, §8):
the student's two closing notes from the tick, and the teacher's note at the student's tap,
as Telegram renders them. All three are silent and plain text (a name is never markup);
"confirmed" offers `[⭐ Make main]` only from the second teacher; "no answer yet" reads the
same whatever happened on the teacher's side and leads to that shala's question. The screens
behind the buttons are in `test_teacher_requests_screens_bot.py`."""

import re
from uuid import UUID, uuid4

import pytest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup

from tests.bots.test_moon_bot import _notifier  # pyright: ignore[reportPrivateUsage]
from tristhana.application.ports.notifications import (
    DeliveryStatus,
    Recipient,
    RequestClosed,
    TeacherAsked,
)
from tristhana.bots.telegram import home_callbacks, shalas_callbacks
from tristhana.bots.telegram import teacher_links_callbacks as links_cb
from tristhana.domain.locale import Locale
from tristhana.domain.teacher_requests import Closing
from tristhana.infrastructure.i18n.fluent import FluentTranslator

T = FluentTranslator()
TEACHER, SHALA = uuid4(), uuid4()


def _note(
    closing: Closing, name: str | None = "Anna", make_main: bool = False, teacher: UUID = TEACHER
) -> RequestClosed:
    return RequestClosed(closing, teacher, name, SHALA, make_main)


async def _send(
    monkeypatch: pytest.MonkeyPatch, note: RequestClosed, locale: Locale = "en"
) -> SendMessage:
    notifier, sent = _notifier(monkeypatch, None)
    result = await notifier.deliver(Recipient("42", locale), note)
    assert result.status is DeliveryStatus.SENT
    [method] = sent
    assert isinstance(method, SendMessage)
    return method


def _buttons(method: SendMessage) -> list[list[tuple[str, str | None]]]:
    markup = method.reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]


@pytest.mark.parametrize("closing", list(Closing))
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_a_closing_note_is_silent_plain_text_to_the_student(
    monkeypatch: pytest.MonkeyPatch, closing: Closing, locale: Locale
) -> None:
    method = await _send(monkeypatch, _note(closing, "<b>Anna</b>"), locale)

    assert method.chat_id == 42
    assert method.disable_notification is True
    assert method.parse_mode is None  # the name is the teacher's own text, never markup
    assert "<b>Anna</b>" in method.text
    assert _buttons(method)[-1] == [(T.t(locale, "menu-open"), home_callbacks.MENU)]


async def test_confirmed_in_english_and_russian(monkeypatch: pytest.MonkeyPatch) -> None:
    en = await _send(monkeypatch, _note(Closing.CONFIRMED), "en")
    ru = await _send(monkeypatch, _note(Closing.CONFIRMED, "Анна"), "ru")

    assert en.text == T.t("en", "request-confirmed", name="Anna")
    assert ru.text == T.t("ru", "request-confirmed", name="Анна")
    assert "Anna" in en.text
    assert "Анна" in ru.text
    assert en.text != "request-confirmed" != ru.text


async def test_make_main_only_from_the_second_teacher(monkeypatch: pytest.MonkeyPatch) -> None:
    first = await _send(monkeypatch, _note(Closing.CONFIRMED, make_main=False))
    second = await _send(monkeypatch, _note(Closing.CONFIRMED, make_main=True))

    menu = [(T.t("en", "menu-open"), home_callbacks.MENU)]
    assert _buttons(first) == [menu]
    assert _buttons(second) == [
        [(T.t("en", "links-make-main"), links_cb.person("p", TEACHER))],
        menu,
    ]


@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_no_answer_names_the_teacher_and_offers_another_one_in_that_shala(
    monkeypatch: pytest.MonkeyPatch, locale: Locale
) -> None:
    # `make_main` is never set on this note; even if it were, the button stays off.
    method = await _send(monkeypatch, _note(Closing.NO_ANSWER, "Anna", make_main=True), locale)

    assert method.text == T.t(locale, "request-no-answer", name="Anna")
    assert "Anna" in method.text
    assert _buttons(method) == [
        [(T.t(locale, "request-pick-another"), shalas_callbacks.on_shala("t", SHALA))],
        [(T.t(locale, "menu-open"), home_callbacks.MENU)],
    ]


@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_no_answer_never_says_no(monkeypatch: pytest.MonkeyPatch, locale: Locale) -> None:
    method = await _send(monkeypatch, _note(Closing.NO_ANSWER), locale)

    assert not re.search("отклон|отказ|declin|reject|refus", method.text.lower())


@pytest.mark.parametrize("closing", list(Closing))
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_a_teacher_without_a_name_reads_as_no_name(
    monkeypatch: pytest.MonkeyPatch, closing: Closing, locale: Locale
) -> None:
    method = await _send(monkeypatch, _note(closing, None), locale)

    assert T.t(locale, "link-no-name") in method.text


@pytest.mark.parametrize("closing", list(Closing))
async def test_every_button_fits_and_the_text_fits_with_a_long_name(
    monkeypatch: pytest.MonkeyPatch, closing: Closing
) -> None:
    method = await _send(monkeypatch, _note(closing, "Я" * 64, make_main=True), "ru")

    assert len(method.text) <= 4096
    for row in _buttons(method):
        for _, data in row:
            assert data is not None
            assert len(data.encode()) <= 64


async def test_a_blocked_bot_is_reported_as_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.methods import GetMe

    error = TelegramForbiddenError(method=GetMe(), message="bot was blocked by the user")
    notifier, _ = _notifier(monkeypatch, error)

    result = await notifier.deliver(Recipient("42", "en"), _note(Closing.CONFIRMED))

    assert result.status is DeliveryStatus.BLOCKED


# The teacher's note at the student's tap

STUDENT = uuid4()


async def _ask(
    monkeypatch: pytest.MonkeyPatch,
    locale: Locale = "en",
    name: str | None = "Ash",
    shala: str = "Ashtanga Almaty",
    waiting: int = 1,
) -> SendMessage:
    notifier, sent = _notifier(monkeypatch, None)
    asked = TeacherAsked(STUDENT, name, shala, waiting)
    result = await notifier.tell_teacher_asked(Recipient("42", locale), asked)
    assert result.status is DeliveryStatus.SENT
    [method] = sent
    assert isinstance(method, SendMessage)
    return method


@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_the_teachers_note_is_silent_plain_text_with_yes_and_not_my_student(
    monkeypatch: pytest.MonkeyPatch, locale: Locale
) -> None:
    method = await _ask(monkeypatch, locale, "<b>Ash</b>", "<i>Shala</i>")

    assert method.chat_id == 42
    assert method.disable_notification is True
    assert method.parse_mode is None  # both names are other people's text, never markup
    assert method.text == T.t(locale, "request-note", student="<b>Ash</b>", shala="<i>Shala</i>")
    assert "<b>Ash</b>" in method.text
    assert "<i>Shala</i>" in method.text
    assert _buttons(method) == [
        [
            (T.t(locale, "request-yes-mine"), links_cb.person("ra", STUDENT)),
            (T.t(locale, "request-not-mine"), links_cb.person("rn", STUDENT)),
        ]
    ]


@pytest.mark.parametrize(("waiting", "shown"), [(1, False), (2, True), (57, True)])
async def test_see_all_only_from_two_waiting(
    monkeypatch: pytest.MonkeyPatch, waiting: int, shown: bool
) -> None:
    method = await _ask(monkeypatch, waiting=waiting)

    see_all = [(T.t("en", "request-see-all", count=waiting), links_cb.waiting(0))]
    assert (_buttons(method)[-1] == see_all) is shown
    assert len(_buttons(method)) == (2 if shown else 1)


async def test_the_teachers_note_says_to_confirm_only_someone_they_know(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    en = await _ask(monkeypatch, "en")
    ru = await _ask(monkeypatch, "ru")

    assert "only if you know" in en.text
    assert "только если знаешь" in ru.text


async def test_a_student_without_a_name_reads_as_no_name(monkeypatch: pytest.MonkeyPatch) -> None:
    method = await _ask(monkeypatch, name=None)

    assert T.t("en", "link-no-name") in method.text


async def test_the_teachers_note_fits_with_long_names(monkeypatch: pytest.MonkeyPatch) -> None:
    method = await _ask(monkeypatch, "ru", "Я" * 64, "Ш" * 64, waiting=100)

    assert len(method.text) <= 4096
    for row in _buttons(method):
        for _, data in row:
            assert data is not None
            assert len(data.encode()) <= 64


async def test_a_teacher_who_blocked_the_bot_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.methods import GetMe

    error = TelegramForbiddenError(method=GetMe(), message="bot was blocked by the user")
    notifier, _ = _notifier(monkeypatch, error)

    result = await notifier.tell_teacher_asked(
        Recipient("42", "en"), TeacherAsked(STUDENT, "Ash", "Ashtanga Almaty", 1)
    )

    assert result.status is DeliveryStatus.BLOCKED
