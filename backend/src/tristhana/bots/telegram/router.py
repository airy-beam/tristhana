"""Handlers: Telegram update → use case → localized reply. No business logic here.

Handlers return an unexecuted Bot API method: in webhook mode it becomes the HTTP response
(webhook reply, ADR-0012); in polling mode aiogram executes it. `account` is injected by
`AccountMiddleware` (ID-01), so every reply uses the account's locale.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import (
    CallbackQuery,
    Message,
)

from tristhana.application.accounts import EnsureAccount
from tristhana.application.calendar_feed import CalendarFeedUseCases
from tristhana.application.directory_listing import ListingUseCases
from tristhana.application.ports.i18n import Translator
from tristhana.application.teacher_links import LinkUseCases
from tristhana.bots.telegram import days as day_screens
from tristhana.bots.telegram.announcements import AnnouncementScreens, register_announcements
from tristhana.bots.telegram.attendance import AttendanceScreens, register_attendance
from tristhana.bots.telegram.calendar_feed import FeedScreens
from tristhana.bots.telegram.classes import ScheduleScreens, register_classes
from tristhana.bots.telegram.data import register_data
from tristhana.bots.telegram.diary import register_diary_reply
from tristhana.bots.telegram.directory_listing import ListingScreens, register_listing
from tristhana.bots.telegram.middleware import AccountMiddleware
from tristhana.bots.telegram.moon import register_moon
from tristhana.bots.telegram.remind import register_remind
from tristhana.bots.telegram.rest import register_rest
from tristhana.bots.telegram.runtime import (
    CheckInUseCases,
    DataUseCases,
    DayUseCases,
    DiaryUseCases,
    MoonUseCases,
    PracticeUseCases,
    ProgressionUseCases,
    RemindUseCases,
    RestUseCases,
    SettingsUseCases,
)
from tristhana.bots.telegram.settings import register_settings
from tristhana.bots.telegram.shalas import ShalaScreens, register_shalas
from tristhana.bots.telegram.start import StartScreens, register_start
from tristhana.bots.telegram.teacher_links import LinkScreens, register_links
from tristhana.bots.telegram.tour import register_tour
from tristhana.domain.accounts import Account


def build_router(
    ensure: EnsureAccount,
    days: DayUseCases,
    practices: PracticeUseCases,
    moon: MoonUseCases,
    remind: RemindUseCases,
    settings: SettingsUseCases,
    translator: Translator,
    miniapp_url: str = "",
    rest: RestUseCases | None = None,
    check_ins: CheckInUseCases | None = None,
    diary: DiaryUseCases | None = None,
    progression: ProgressionUseCases | None = None,
    data: DataUseCases | None = None,
    links: LinkUseCases | None = None,
    bot_username: str = "",
    calendar: CalendarFeedUseCases | None = None,
    listings: ListingUseCases | None = None,
) -> Router:
    router = Router(name="tristhana")
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    accounts = AccountMiddleware(ensure, translator)
    router.message.middleware(accounts)
    router.callback_query.middleware(accounts)

    screens = day_screens.register(
        router, days, practices, translator, remind, miniapp_url, check_ins, diary, progression
    )
    start = StartScreens(screens, settings, translator, miniapp_url)
    invites = shalas = None
    if links is not None:  # ID-04 (always wired by the app)
        invites = LinkScreens(links, start, settings, translator, miniapp_url, bot_username)
        if links.shalas is not None:  # SC-01
            shalas = ShalaScreens(links.shalas, start, invites, settings, translator, bot_username)
    register_start(router, start, invites, shalas)
    if invites is not None:
        register_links(router, invites)
        if listings is not None:  # ID-05: the status screen, /admin, the line on the cards
            invites.listings = ListingScreens(listings, translator, miniapp_url)
            register_listing(router, invites.listings, translator)
        if links is not None and links.announcements is not None and links.shalas is not None:
            ann = AnnouncementScreens(links.announcements, translator, links.shalas.clock)
            invites.announcements = ann  # NT-03: pins and buttons on the cards
            register_announcements(router, ann, invites.overview)
    if shalas is not None:
        register_shalas(router, shalas)
        if links is not None and links.shalas is not None and links.shalas.classes is not None:
            feed = (
                None
                if calendar is None
                else FeedScreens(calendar, links.shalas, translator)  # SC-06
            )
            schedule = ScheduleScreens(
                links.shalas.classes,
                shalas,
                invites,  # type: ignore[arg-type]  # set with shalas
                translator,
                links.shalas.cities,
                links.shalas.clock,
                feed,
                attendance=links.shalas.attendance is not None,  # SC-05
            )
            if links.shalas.attendance is not None:
                attendance = AttendanceScreens(
                    links.shalas.attendance, translator, links.shalas.cities
                )
                register_attendance(router, attendance)
            register_classes(router, schedule)
    register_tour(router, start, translator, miniapp_url)
    entry = calendar is not None and calendar.available  # SC-06: "📅 Add to calendar" rows
    register_moon(router, moon, translator, entry)
    remind_screens = register_remind(router, remind, screens, translator, rest)
    if rest is not None:  # WH-01 rest periods (always wired by the app)
        register_rest(router, rest, remind, screens, remind_screens, translator)
    register_settings(router, settings, translator, miniapp_url, data is not None, entry)
    if data is not None:  # ST-09: My data (export, delete)
        register_data(router, data, translator)
    if screens.diary is not None:  # after every command handler (PR-07 review)
        register_diary_reply(router, screens.diary)

    @router.callback_query()
    async def on_unknown_callback(callback: CallbackQuery) -> AnswerCallbackQuery:  # pyright: ignore[reportUnusedFunction]
        return callback.answer()  # an old or unknown keyboard: stop the spinner, do nothing

    @router.message(F.text)
    async def on_other(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(account.locale, "fallback-text"))

    return router
