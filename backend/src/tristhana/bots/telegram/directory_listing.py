"""The directory listing in the bot (ID-05, ADR-0042).

A teacher sees their status and can remove the line; the form itself is in the Mini App. A
platform admin answers requests behind `/admin`: in no menu, and for anyone else it replies
with the ordinary fallback text, so it can't be probed. The admin opens the public directory
in a browser by a URL button; the server never calls that site.

The line is always its own text line and never part of a button label: a display name can't
hold a line break, so a name can't imitate it. Names, regions and notes are never logged.
"""

from collections.abc import Awaitable
from datetime import date
from urllib.parse import urlencode
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from tristhana.application.directory_listing import ListingUseCases
from tristhana.application.policies import NotFound, Principal
from tristhana.application.ports.directory_listing import PAGE, RequestCard
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.bots.telegram import directory_listing_callbacks as cb
from tristhana.bots.telegram import teacher_links_callbacks as links_cb
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, nothing, show
from tristhana.domain.accounts import Account
from tristhana.domain.directory_listing import (
    DIRECTORY_URL,
    DeclaredLevel,
    ListingMark,
    ListingStatus,
    Outcome,
)
from tristhana.domain.locale import Locale
from tristhana.domain.teacher_links import shown_name


def _when(day: date) -> DateArg:
    return DateArg(day, style="month")


def level_name(t: Translator, locale: Locale, level: DeclaredLevel) -> str:
    return t.t(locale, "listing-level-name", level=level.value)


def mark_line(t: Translator, locale: Locale, mark: ListingMark) -> str:
    """The checked fact, on its own line. Never the level."""
    return t.t(locale, "listing-mark", listed=mark.name_as_listed, when=_when(mark.checked_on))


def card_lines(t: Translator, locale: Locale, mark: ListingMark) -> list[str]:
    """The teacher card: the line, the level in the teacher's own words (no ✔), and what
    the line does and doesn't say. The level never shows on the consent screen or in lists."""
    lines = [mark_line(t, locale, mark)]
    if mark.level is not None:
        lines.append(t.t(locale, "listing-level", level=level_name(t, locale, mark.level)))
    return lines


def requested_note(t: Translator, locale: Locale) -> Screen:
    """To an admin: a request is waiting. It carries no name."""
    return Screen(t.t(locale, "admin-listing-new"), InlineKeyboardMarkup(inline_keyboard=[]))


def checked_note(
    t: Translator, locale: Locale, outcome: Outcome, listed: str, was_listed: bool
) -> Screen:
    """To the teacher: the answer, in their language."""
    if outcome is Outcome.LISTED:
        key = "listing-note-listed"
    else:
        key = "listing-note-ended" if was_listed else "listing-note-not-found"
    rows = [[button(t, locale, "listing-open", cb.mine("o"))]]
    return Screen(t.t(locale, key, listed=listed), InlineKeyboardMarkup(inline_keyboard=rows))


class ListingScreens:
    def __init__(self, listings: ListingUseCases, translator: Translator, app: str) -> None:
        self._l = listings
        self._t = translator
        self._app = app

    @property
    def available(self) -> bool:
        return self._l.available

    def checks(self, principal: Principal) -> bool:
        return self._l.checks(principal)

    def entry_button(self, locale: Locale) -> InlineKeyboardButton:
        """The quiet row on the invite screen."""
        return button(self._t, locale, "listing-open", cb.mine("o"))

    def _button(self, locale: Locale, key: str, data: str) -> InlineKeyboardButton:
        return button(self._t, locale, key, data)

    # My own status (anyone).
    async def status(self, principal: Principal, lead: str | None = None) -> Screen:
        locale = principal.account.locale
        found = await self._l.get.execute(principal)
        t = self._t
        lines = [lead] if lead else []
        lines.append(t.t(locale, "listing-title"))
        removable = False
        if found is None or found.status is ListingStatus.WITHDRAWN:
            lines += [t.t(locale, "listing-intro"), t.t(locale, "listing-how")]
        else:
            removable = True
            name = found.name_as_listed or ""
            if found.status is ListingStatus.PENDING:
                lines.append(t.t(locale, "listing-pending", listed=name))
            elif found.status is ListingStatus.NOT_FOUND:
                lines.append(t.t(locale, "listing-not-found", listed=name))
            elif found.checked_on is not None:
                mark = ListingMark(name, found.checked_on, found.level)
                lines.append("\n".join(card_lines(t, locale, mark)))
                lines.append(t.t(locale, "listing-listed-hint"))
        rows: list[list[InlineKeyboardButton]] = []
        if self._app and self._l.available:  # off: no form, but my row can still be removed
            query = urlencode({"open": "listing"})
            url = f"{self._app}{'&' if '?' in self._app else '?'}{query}"
            rows.append(
                [InlineKeyboardButton(text=t.t(locale, "listing-app"), web_app=WebAppInfo(url=url))]
            )
        if removable:
            rows.append([self._button(locale, "listing-remove", cb.mine("w"))])
        rows.append([self._button(locale, "log-back", links_cb.plain("i"))])
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def ask_remove(self, principal: Principal) -> Screen:
        locale = principal.account.locale
        rows = [
            [self._button(locale, "listing-remove-yes", cb.mine("wy"))],
            [self._button(locale, "log-back", cb.mine("o"))],
        ]
        return Screen(
            self._t.t(locale, "listing-remove-ask"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    async def remove(self, principal: Principal) -> Screen:
        await self._l.withdraw.execute(principal)
        return await self.status(principal, self._t.t(principal.account.locale, "listing-removed"))

    # The review (platform admins only; every call re-checks the policy in the use case).
    async def requests(
        self, principal: Principal, listed: bool, page: int, lead: str | None = None
    ) -> Screen:
        locale = principal.account.locale
        t = self._t
        found = await self._l.requests.execute(principal, listed, page)
        if not found.rows and page > 0:
            page = 0
            found = await self._l.requests.execute(principal, listed, 0)
        lines = [lead] if lead else []
        lines.append(t.t(locale, "admin-listing-title", waiting=found.waiting, listed=found.listed))
        if found.oldest_check is not None:
            lines.append(t.t(locale, "admin-listing-oldest", when=_when(found.oldest_check)))
        if listed:
            lines.append(t.t(locale, "admin-listing-listed-title"))
        if not found.rows:
            lines.append(t.t(locale, "admin-listing-empty"))
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text=r.name_as_listed[:60], callback_data=cb.admin_card(r.account_id)
                )
            ]
            for r in found.rows
        ]
        total = found.listed if listed else found.waiting
        last = max(0, (total - 1) // PAGE)
        turn: list[InlineKeyboardButton] = []
        if page > 0:
            turn.append(self._button(locale, "page-prev", cb.admin_list(listed, page - 1)))
        if page < last:
            turn.append(self._button(locale, "page-next", cb.admin_list(listed, page + 1)))
        if turn:
            rows.append(turn)
        other = "admin-listing-waiting" if listed else "admin-listing-recheck"
        rows.append([self._button(locale, other, cb.admin_list(not listed, 0))])
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _card_text(self, locale: Locale, card: RequestCard) -> str:
        t = self._t
        found = card.listing
        name = shown_name(card.display_name) or t.t(locale, "link-no-name")
        lines = [
            t.t(locale, "admin-listing-card-name", name=name),
            t.t(locale, "admin-listing-card-listed", listed=found.name_as_listed or ""),
            t.t(locale, "admin-listing-card-region", region=found.region or ""),
        ]
        if found.level is not None:
            level = level_name(t, locale, found.level)
            lines.append(t.t(locale, "admin-listing-card-level", level=level))
        if found.note:
            lines.append(t.t(locale, "admin-listing-card-note", note=found.note))
        sent = DateArg(found.requested_at.date(), with_year=True)
        lines.append(t.t(locale, "admin-listing-card-requested", date=sent))
        if found.checked_on is not None:
            when = _when(found.checked_on)
            lines.append(t.t(locale, "admin-listing-card-checked", when=when))
        return "\n".join(lines)

    async def card(self, principal: Principal, id: UUID) -> Screen:
        locale = principal.account.locale
        card = await self._l.card.execute(principal, id)
        if card is None or card.listing.status is ListingStatus.NOT_FOUND:
            return await self.requests(principal, False, 0)
        found = card.listing
        listed = found.status is ListingStatus.LISTED
        rev = found.revision
        rows = [
            [
                InlineKeyboardButton(
                    text=self._t.t(locale, "admin-listing-open-directory"), url=DIRECTORY_URL
                )
            ],
            [
                self._button(
                    locale,
                    "admin-listing-still-listed" if listed else "admin-listing-listed",
                    cb.decide("y", id, rev),
                )
            ],
            [
                self._button(
                    locale,
                    "admin-listing-ended" if listed else "admin-listing-not-found",
                    cb.decide("n", id, rev),
                )
            ],
            [self._button(locale, "log-back", cb.admin_list(listed, 0))],
        ]
        return Screen(
            self._card_text(locale, card),
            InlineKeyboardMarkup(inline_keyboard=rows),
            no_preview=True,  # a note may hold a link: no crawler fetches it
        )

    async def ask_not_found(self, principal: Principal, tap: cb.Decide) -> Screen:
        locale = principal.account.locale
        card = await self._l.card.execute(principal, tap.id)
        if card is None or card.listing.revision != tap.revision:
            return await self._stale(principal)
        listed = card.listing.status is ListingStatus.LISTED
        key = "admin-listing-ended-ask" if listed else "admin-listing-not-found-ask"
        rows = [
            [self._button(locale, "admin-listing-yes", cb.decide("ny", tap.id, tap.revision))],
            [self._button(locale, "log-back", cb.admin_card(tap.id))],
        ]
        text = self._t.t(locale, key, listed=card.listing.name_as_listed or "")
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def _stale(self, principal: Principal) -> Screen:
        lead = self._t.t(principal.account.locale, "admin-listing-stale")
        return await self.requests(principal, False, 0, lead)

    async def decide(self, principal: Principal, tap: cb.Decide) -> Screen:
        locale = principal.account.locale
        outcome = Outcome.LISTED if tap.action == "y" else Outcome.NOT_FOUND
        decided = await self._l.decide.execute(principal, tap.id, tap.revision, outcome)
        if decided is None:
            return await self._stale(principal)
        key = (
            "admin-listing-done-listed"
            if outcome is Outcome.LISTED
            else ("admin-listing-done-not-found")
        )
        lead = self._t.t(locale, key, listed=decided.name_as_listed)
        return await self.requests(principal, decided.was_listed, 0, lead)

    def work(self, tap: cb.ListingTap, principal: Principal) -> Awaitable[Screen]:
        match tap:
            case cb.Mine("w"):
                return _now(self.ask_remove(principal))
            case cb.Mine("wy"):
                return self.remove(principal)
            case cb.Mine():
                return self.status(principal)
            case cb.AdminList(listed, page):
                return self.requests(principal, listed, page)
            case cb.AdminCard(id):
                return self.card(principal, id)
            case cb.Decide("n"):
                return self.ask_not_found(principal, tap)
            case cb.Decide():
                return self.decide(principal, tap)


async def _now(screen: Screen) -> Screen:
    return screen


def register_listing(router: Router, screens: ListingScreens, translator: Translator) -> None:
    @router.message(Command("admin"))
    async def on_admin(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        principal = Principal(account)
        if not screens.available or not screens.checks(principal):
            # The same reply as any unknown text: the command can't be probed.
            return message.answer(translator.t(account.locale, "fallback-text"))
        screen = await screens.requests(principal, False, 0)
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{cb.PREFIX}:"))
    async def on_listing(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        tap = cb.decode(callback.data)
        principal = Principal(account)
        admin_tap = not isinstance(tap, cb.Mine)
        refused = admin_tap and not (screens.available and screens.checks(principal))
        if tap is None or refused:
            await answered(callback, nothing())  # forged, old, or not an admin: only answers
            return None
        try:
            screen = await answered(callback, screens.work(tap, principal))
        except NotFound:
            return None
        return show(callback, screen)
