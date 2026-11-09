"""Announcements in the bot (NT-03, ADR-0038): the pushed message (rendered by the notifier),
the feed screen for one source, and mute/unmute. Composing is in the Mini App (Q176). The
text is plain, never parsed (no parse_mode), and never logged."""

from collections.abc import Awaitable, Callable
from datetime import date, datetime

from aiogram import F, Router
from aiogram.methods import EditMessageReplyMarkup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.announcements import AnnouncementUseCases
from tristhana.application.policies import NotFound, Principal
from tristhana.application.ports.announcements import FeedItem
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.application.ports.notifications import Announcement
from tristhana.application.ports.storage import Clock
from tristhana.bots.telegram import announcements_callbacks as cb
from tristhana.bots.telegram import shalas_callbacks, teacher_links_callbacks
from tristhana.bots.telegram.announcements_callbacks import Where
from tristhana.bots.telegram.screens import Reply, Screen, answered, nothing, show
from tristhana.domain.accounts import Account
from tristhana.domain.announcements import Source, SourceKind
from tristhana.domain.days import local_today, provisional_zone
from tristhana.domain.locale import Locale
from tristhana.domain.teacher_links import shown_name

# Three whole items always fit one message (3 x (1000 + two short lines) < 4096), so no
# item is ever cut and none is lost between pages.
PAGE = 3
PIN_PREVIEW = 200

type Gone = Callable[[Principal], Awaitable[Screen]]  # `/teachers` again: the source is gone
type AnnouncementReply = Reply | EditMessageReplyMarkup


def _name(t: Translator, locale: Locale, name: str | None) -> str:
    return shown_name(name) or t.t(locale, "link-no-name")


def head(
    t: Translator, locale: Locale, source: Source, source_name: str | None, author: str | None
) -> str:
    """`📣 Anna · your teacher`, `📣 Ashtanga Almaty · Anna`, or the shala alone once the
    author has left its staff."""
    if source.kind is SourceKind.TEACHER:
        return t.t(locale, "ann-head-teacher", name=_name(t, locale, source_name))
    shala = source_name or ""
    if author is None:
        return t.t(locale, "ann-head-shala-only", shala=shala)
    return t.t(locale, "ann-head-shala", shala=shala, name=_name(t, locale, author))


def mute_row(
    t: Translator, locale: Locale, source: Source, muted: bool
) -> list[InlineKeyboardButton]:
    key, data = (
        ("ann-unmute", cb.mute(source, False, "n"))
        if muted
        else (
            "ann-mute",
            cb.mute(source, True, "n"),
        )
    )
    return [
        InlineKeyboardButton(text=t.t(locale, key), callback_data=data),
        InlineKeyboardButton(text=t.t(locale, "ann-list"), callback_data=cb.feed(source)),
    ]


def message_screen(t: Translator, locale: Locale, n: Announcement) -> Screen:
    """The pushed message, in the recipient's locale; the text stays as written."""
    text = f"{head(t, locale, n.source, n.source_name, n.author_name)}\n{n.text}"
    markup = InlineKeyboardMarkup(inline_keyboard=[mute_row(t, locale, n.source, muted=False)])
    return Screen(text, markup, no_preview=True)


def back_data(source: Source) -> str:
    if source.kind is SourceKind.TEACHER:
        return teacher_links_callbacks.person("c", source.id)
    return shalas_callbacks.on_shala("c", source.id)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: max(1, limit - 1)].rstrip()}…"


class AnnouncementScreens:
    def __init__(self, use_cases: AnnouncementUseCases, translator: Translator, clock: Clock):
        self._a = use_cases
        self._t = translator
        self._clock = clock

    @property
    def translator(self) -> Translator:
        return self._t

    def _local(self, account: Account, at: datetime) -> date:
        return local_today(at, account.timezone or provisional_zone(account.locale))

    def _date(self, account: Account, at: datetime) -> DateArg:
        day = self._local(account, at)
        today = self._local(account, self._clock.now())
        return DateArg(day, with_year=day.year != today.year)

    async def pin_line(self, principal: Principal, source: Source) -> str | None:
        """The live pin of one source for its card (`📌 <first 200 chars>`), if any."""
        try:
            feed = await self._a.feed.execute(principal, source, 0, 1)
        except NotFound:
            return None
        if not feed.items or feed.items[0].pinned_until is None:
            return None
        return f"📌 {_clip(feed.items[0].text, PIN_PREVIEW)}"

    def card_button(self, locale: Locale, source: Source) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=self._t.t(locale, "ann-list"), callback_data=cb.feed(source)
        )

    def _item(self, account: Account, item: FeedItem) -> str:
        locale = account.locale
        lines: list[str] = []
        if item.pinned_until is not None:
            until = self._local(account, item.pinned_until)
            lines.append(self._t.t(locale, "ann-pinned-until", date=DateArg(until)))
        by = item.author_name if item.author_name is not None else item.source_name
        lines.append(
            self._t.t(
                locale,
                "ann-item",
                date=self._date(account, item.created_at),
                name=_name(self._t, locale, by),
            )
        )
        lines.append(item.text)
        return "\n".join(lines)

    async def feed(self, principal: Principal, source: Source, page: int) -> Screen | None:
        """None: not one of the caller's sources (any more)."""
        account = principal.account
        locale = account.locale
        try:
            feed = await self._a.feed.execute(principal, source, page * PAGE, PAGE)
            if not feed.items and page > 0:
                page = 0
                feed = await self._a.feed.execute(principal, source, 0, PAGE)
        except NotFound:
            return None
        found = feed.sources[0] if feed.sources else None
        muted = found.muted if found else False
        name = found.name if found else None
        if source.kind is SourceKind.TEACHER:
            name = _name(self._t, locale, name)
        parts = [self._t.t(locale, "ann-list-title", source=name or "")]
        if not feed.items:
            parts.append(self._t.t(locale, "ann-list-empty"))
        parts += [self._item(account, i) for i in feed.items]
        toggle = cb.mute(source, not muted, "l")
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text=self._t.t(locale, "ann-unmute" if muted else "ann-mute"),
                    callback_data=toggle,
                )
            ]
        ]
        turn: list[InlineKeyboardButton] = []
        if page > 0:
            turn.append(
                InlineKeyboardButton(
                    text=self._t.t(locale, "page-prev"), callback_data=cb.feed(source, page - 1)
                )
            )
        if feed.more and page < 99:
            turn.append(
                InlineKeyboardButton(
                    text=self._t.t(locale, "page-next"), callback_data=cb.feed(source, page + 1)
                )
            )
        if turn:
            rows.append(turn)
        rows.append(
            [
                InlineKeyboardButton(
                    text=self._t.t(locale, "log-back"), callback_data=back_data(source)
                )
            ]
        )
        return Screen(
            "\n\n".join(parts), InlineKeyboardMarkup(inline_keyboard=rows), no_preview=True
        )

    async def mute(self, principal: Principal, source: Source, muted: bool) -> bool:
        """False: not the caller's teacher or shala (any more)."""
        try:
            await self._a.mute.execute(principal, source, muted)
        except NotFound:
            return False
        return True

    def muted_toast(self, locale: Locale, muted: bool) -> str:
        return self._t.t(locale, "ann-muted" if muted else "ann-unmuted")


def register_announcements(router: Router, screens: AnnouncementScreens, gone: Gone) -> None:
    @router.callback_query(F.data.startswith(f"{cb.PREFIX}:"))
    async def on_announcement(  # pyright: ignore[reportUnusedFunction]
        callback: CallbackQuery, account: Account
    ) -> AnnouncementReply | None:
        tap = cb.decode(callback.data)
        if tap is None:
            await answered(callback, nothing())
            return None
        principal = Principal(account)
        match tap:
            case cb.List(source, page):
                screen = await answered(callback, screens.feed(principal, source, page))
                if screen is None:
                    screen = await gone(principal)
                return show(callback, screen)
            case cb.Mute(source, muted, where):
                return await _mute(callback, principal, screens, gone, source, muted, where)


async def _mute(
    callback: CallbackQuery,
    principal: Principal,
    screens: AnnouncementScreens,
    gone: Gone,
    source: Source,
    muted: bool,
    where: Where,
) -> AnnouncementReply | None:
    locale = principal.account.locale
    ok = await screens.mute(principal, source, muted)
    if not ok:
        await callback.answer()
        return show(callback, await gone(principal))
    await callback.answer(screens.muted_toast(locale, muted))  # the toast is the answer
    message = callback.message
    if where == "n" and isinstance(message, Message):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[mute_row(screens.translator, locale, source, muted)]
        )
        return message.edit_reply_markup(reply_markup=markup)
    screen = await screens.feed(principal, source, 0)
    if screen is None:
        screen = await gone(principal)
    return show(callback, screen)
