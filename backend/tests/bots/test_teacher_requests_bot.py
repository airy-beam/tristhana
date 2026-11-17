"""Teacher requests in the bot, the part that ships with the tick (ID-07 spec §2, §8): the
student's two closing notes as Telegram renders them. Both are silent and plain text (a name
is never markup); "confirmed" offers `[⭐ Make main]` only from the second teacher; "no answer
yet" reads the same whatever happened on the teacher's side. The question, the teacher's note
and the waiting list come with their screens."""

import re
from uuid import UUID, uuid4

import pytest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup

from tests.bots.test_moon_bot import _notifier  # pyright: ignore[reportPrivateUsage]
from tristhana.application.ports.notifications import DeliveryStatus, Recipient, RequestClosed
from tristhana.bots.telegram import home_callbacks
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
async def test_no_answer_names_the_teacher_and_offers_only_the_menu(
    monkeypatch: pytest.MonkeyPatch, locale: Locale
) -> None:
    # `make_main` is never set on this note; even if it were, the button stays off.
    method = await _send(monkeypatch, _note(Closing.NO_ANSWER, "Anna", make_main=True), locale)

    assert method.text == T.t(locale, "request-no-answer", name="Anna")
    assert "Anna" in method.text
    assert _buttons(method) == [[(T.t(locale, "menu-open"), home_callbacks.MENU)]]


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
