"""Shared pieces of the inline-keyboard screens (days, practice details)."""

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import date, time, timedelta
from urllib.parse import urlencode

from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    WebAppInfo,
)

from tristhana.application.ports.i18n import DateArg, TimeArg, Translator
from tristhana.bots.telegram import home_callbacks
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City

log = logging.getLogger(__name__)

type Reply = SendMessage | EditMessageText


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    markup: InlineKeyboardMarkup
    # SC-06: a screen showing a secret link: Telegram's preview crawler must not fetch it.
    no_preview: bool = False


def button(
    t: Translator, locale: Locale, key: str, data: str, mark: bool = False
) -> InlineKeyboardButton:
    text = t.t(locale, key)
    return InlineKeyboardButton(text=f"✓ {text}" if mark else text, callback_data=data)


def menu_row(t: Translator, locale: Locale) -> list[InlineKeyboardButton]:
    """`[☰ Menu]`: the last row of every top-level screen (UI-06)."""
    return [button(t, locale, "menu-open", home_callbacks.MENU)]


# Every `open` value the bot builds (`app_url`). A test pins this set against the `case`
# labels of the Mini App's `launchNav` (`miniapp/src/shell/nav.ts`), and the bot's literal
# `app_url(…, "<open>")` calls against this set.
APP_OPEN = frozenset(
    {
        "practice",  # the Menu's "📊 My practice"
        "new-shala",  # "🏛 Create a shala"
        "announce",  # "📣 Announce" (`shala=` optional)
        "listing",  # the directory listing (ID-05)
        "settings",  # "⚙️ More in the app"
        # UI-06 stage 6 (spec §2):
        "shala",  # a shala's card (`shala=`), or the Shala root without one
        "class",  # the card with a new class form (`shala=`)
        "edit-shala",  # the card with its edit form (`shala=`)
        "schedule",  # My schedule's full week
    }
)


def app_url(base: str, open: str | None = None, **params: str | None) -> str:
    """The Mini App's URL, opening straight on a screen: `…?open=new-shala`. The one place
    these URLs are built (UI-06). The `open` values (`APP_OPEN`) are a contract with the Mini
    App (`launchNav` in `shell/nav.ts`), and old messages keep their URLs: never rename one.
    Unknown values open Today. A parameter that is None is left out.

    - `practice`, `new-shala`, `listing`, `settings`, `schedule`: that screen;
    - `announce` with an optional `shala=<uuid>`: the message form (over that shala's card);
    - `shala` with an optional `shala=<uuid>`: that shala's card, or the Shala root;
    - `class` / `edit-shala` with `shala=<uuid>`: the card with a new class form / its edit
      form open. A bad or missing id opens the Shala root.
    """
    query = {"open": open} | params
    given = urlencode({k: v for k, v in query.items() if v is not None})
    if not given:
        return base
    return f"{base}{'&' if '?' in base else '?'}{given}"


def guide_url(site: str, locale: Locale, page: str = "") -> str:
    """A page of the public guide (UI-05) in the person's language: the English pages are at
    the root, the Russian ones under /ru/. The Mini App's twin is `guideUrl` in `guide.ts`."""
    return f"{site.rstrip('/')}{'/ru/' if locale == 'ru' else '/'}{page}"


def app_button(t: Translator, locale: Locale, key: str, url: str) -> InlineKeyboardButton:
    """Opens the Mini App (which also records the device time zone, ID-01). `key` says what
    opens ("🏛 Shala in the app", UI-06 stage 6 C1)."""
    return InlineKeyboardButton(text=t.t(locale, key), web_app=WebAppInfo(url=url))


def day_label(t: Translator, locale: Locale, day: date, today: date) -> str:
    rel = "today" if day == today else "yesterday" if day == today - timedelta(1) else "other"
    return t.t(locale, "day-label", rel=rel, date=DateArg(day, with_year=day.year != today.year))


def zone_label(
    t: Translator,
    locale: Locale,
    zone: str,
    today: date,
    city: City | None,
    viewer: str | None = None,
) -> str:
    """The zone as a time label minus the time: "Astana" for a viewer in that zone,
    "Astana (UTC+5)" (the offset today) for anyone else (ADR-0044). Without `viewer` the
    offset always shows: that is for text saying what a zone is (the Settings city row while
    no city is chosen, the travel prompt, a daylight-saving day row), where the offset is the
    information."""
    label = t.t(locale, "time-label", time=TimeArg(today, time(12), zone, city, viewer))
    return label.split(" ", 1)[1] if " " in label else label


async def answered[T](callback: CallbackQuery, work: Awaitable[T]) -> T:
    """Run `work` while answering the callback in parallel (stops the spinner); both are
    awaited before the webhook response, since Cloud Run throttles the CPU afterwards."""
    answering = asyncio.ensure_future(_answer(callback))
    try:
        return await work
    finally:
        await answering


async def nothing() -> None:
    """`answered` work for a tap that changes nothing (old or forged data)."""
    return None


async def _answer(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception as e:  # the edit still goes out; a spinner is not worth a failure
        log.warning("answerCallbackQuery failed: %s", type(e).__name__)


def show(callback: CallbackQuery, screen: Screen) -> Reply:
    message = callback.message
    preview = LinkPreviewOptions(is_disabled=True) if screen.no_preview else None
    if isinstance(message, Message):
        return message.edit_text(
            screen.text, reply_markup=screen.markup, link_preview_options=preview
        )
    # Too old to edit (InaccessibleMessage): send the screen as a new message.
    return SendMessage(
        chat_id=callback.from_user.id,
        text=screen.text,
        reply_markup=screen.markup,
        link_preview_options=preview,
    )
