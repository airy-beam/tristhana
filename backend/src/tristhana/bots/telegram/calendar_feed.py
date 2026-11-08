"""My calendar link in the bot (SC-06, ADR-0036): show it, create it, make a new one, turn it
off; a new link and turning off ask first. The link is plain text in my own chat (Q151), with
the Google and Apple/Outlook buttons as https URLs (Telegram opens no webcal://, Q152).
Stateless (ADR-0008): a stale confirm acts on the current link only.
"""

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from tristhana.application.calendar_feed import CalendarFeedUseCases, feed_urls
from tristhana.application.policies import Principal
from tristhana.application.ports.calendar_feed import FeedLink
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.application.shalas import ShalaUseCases
from tristhana.bots.telegram import classes_callbacks as cb
from tristhana.bots.telegram.screens import Screen
from tristhana.domain.locale import Locale


def entry_button(translator: Translator, locale: Locale) -> InlineKeyboardButton:
    """The "📅 Add to calendar" row on /schedule, /moon and /settings."""
    return InlineKeyboardButton(text=translator.t(locale, "feed-open"), callback_data=cb.feed("s"))


class FeedScreens:
    def __init__(
        self, feed: CalendarFeedUseCases, shalas: ShalaUseCases, translator: Translator
    ) -> None:
        self._f, self._shalas, self._t = feed, shalas, translator

    @property
    def available(self) -> bool:
        return self._f.available

    def _button(self, locale: Locale, key: str, action: cb.FeedAction) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=self._t.t(locale, key), callback_data=cb.feed(action))

    async def handle(self, principal: Principal, action: cb.FeedAction) -> Screen | None:
        if not self._f.available:
            return None
        locale = principal.account.locale
        match action:
            case "s":
                return await self._show(principal)
            case "n":  # a stale "Create" shows the current link: only "New link" rotates
                return self._on(locale, await self._f.create.execute(principal))
            case "r" | "x":
                if await self._f.get.execute(principal) is None:
                    return await self._show(principal)
                key = "feed-rotate-confirm" if action == "r" else "feed-off-confirm"
                yes = self._button(locale, "feed-confirm", "R" if action == "r" else "X")
                back = self._button(locale, "feed-cancel", "s")
                return Screen(
                    self._t.t(locale, key), InlineKeyboardMarkup(inline_keyboard=[[yes, back]])
                )
            case "R":
                if await self._f.get.execute(principal) is None:  # stale: nothing to rotate
                    return await self._show(principal)
                return self._on(locale, await self._f.create.execute(principal, rotate=True))
            case "X":
                await self._f.revoke.execute(principal)
                off = await self._off(principal)
                return Screen(f"{self._t.t(locale, 'feed-off-done')}\n\n{off.text}", off.markup)

    async def _show(self, principal: Principal) -> Screen:
        link = await self._f.get.execute(principal)
        if link is None:
            return await self._off(principal)
        return self._on(principal.account.locale, link)

    async def _off(self, principal: Principal) -> Screen:
        locale = principal.account.locale
        lines = [self._t.t(locale, "feed-title"), self._t.t(locale, "feed-explain")]
        if not await self._shalas.mine.execute(principal):
            lines.append(self._t.t(locale, "feed-moon-only"))
        rows = [[self._button(locale, "feed-create", "n")]]
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _on(self, locale: Locale, link: FeedLink) -> Screen:
        urls = feed_urls(self._f.public_url, link.token)
        checked = (
            self._t.t(locale, "feed-checked", day="none")
            if link.fetched_on is None
            else self._t.t(
                locale,
                "feed-checked",
                day=self._t.t(locale, "day-label", rel="other", date=DateArg(link.fetched_on)),
            )
        )
        lines = [
            self._t.t(locale, "feed-title"),
            self._t.t(locale, "feed-explain"),
            urls.feed,
            self._t.t(locale, "feed-google-phone"),
            self._t.t(locale, "feed-private"),
            checked,
        ]
        rows = [
            [InlineKeyboardButton(text=self._t.t(locale, "feed-google"), url=urls.google)],
            [InlineKeyboardButton(text=self._t.t(locale, "feed-apple"), url=urls.subscribe)],
            [
                InlineKeyboardButton(
                    text=self._t.t(locale, "feed-copy"), copy_text=CopyTextButton(text=urls.feed)
                )
            ],
            [
                self._button(locale, "feed-rotate", "r"),
                self._button(locale, "feed-off", "x"),
            ],
        ]
        return Screen(
            "\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows), no_preview=True
        )
