"""aiogram runtime, built once per process (preloaded at startup when the webhook is on).

This module itself doesn't import aiogram at import time, so `/health`-only paths stay light.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from tristhana.application.accounts import EnsureAccount
from tristhana.application.check_in import ClearCheckIn, SaveCheckIn, SetCheckInTag
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.diary import ClearDiaryNote, GetDiaryNote, SaveDiaryNote
from tristhana.application.moon import (
    GetMoonView,
    NotificationSettingsUseCase,
    SetMoonLocation,
    UpdateMoonReminders,
    UseCityTimezone,
)
from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import Translator
from tristhana.application.practice import (
    ClearPractice,
    CopyLastPractice,
    GetPracticePresets,
    SavePractice,
)
from tristhana.application.progression import (
    DismissNewAsanaHint,
    GetProgression,
    MarkItem,
    MarkNewAsana,
    SetPractice,
    UndoProgression,
)
from tristhana.application.remind import (
    AnswerPracticeOffer,
    LogFromReminder,
    QuickLogSameAsLast,
    UpdatePracticeReminder,
)
from tristhana.application.rest_days import DismissDayOffQuestion, SetDayOff
from tristhana.application.rest_periods import (
    EndRestPeriod,
    RestoreRestPeriod,
    SkipRestPeriod,
    StartRestPeriod,
)
from tristhana.application.settings import UpdateProfile
from tristhana.domain.moon import Cities
from tristhana.domain.practice import PracticeCatalog
from tristhana.domain.progression import Track

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher
    from aiogram.methods import TelegramMethod


@dataclass(frozen=True, slots=True)
class DayUseCases:
    get: GetDays
    set: SetDayStatus
    clear: ClearDayStatus


@dataclass(frozen=True, slots=True)
class PracticeUseCases:
    save: SavePractice
    copy_last: CopyLastPractice
    clear: ClearPractice
    presets: GetPracticePresets
    catalog: PracticeCatalog


@dataclass(frozen=True, slots=True)
class CheckInUseCases:
    """PR-06: the after-practice check-in (shared by the bot and the API)."""

    save: SaveCheckIn
    set_tag: SetCheckInTag
    clear: ClearCheckIn


@dataclass(frozen=True, slots=True)
class DiaryUseCases:
    """PR-07: the diary note per day (shared by the bot and the API)."""

    save: SaveDiaryNote
    get: GetDiaryNote
    clear: ClearDiaryNote


@dataclass(frozen=True, slots=True)
class ProgressionUseCases:
    """PR-08: progression and its celebrations (shared by the bot and the API)."""

    get: GetProgression
    set: SetPractice
    give: MarkNewAsana
    item: MarkItem
    undo: UndoProgression
    dismiss: DismissNewAsanaHint
    track: Track


@dataclass(frozen=True, slots=True)
class MoonUseCases:
    cities: Cities
    view: GetMoonView
    set_location: SetMoonLocation
    use_city_zone: UseCityTimezone
    reminders: UpdateMoonReminders


@dataclass(frozen=True, slots=True)
class RemindUseCases:
    settings: NotificationSettingsUseCase
    update: UpdatePracticeReminder
    offer: AnswerPracticeOffer
    quick_log: QuickLogSameAsLast
    day_off: SetDayOff
    dismiss_day_off: DismissDayOffQuestion


@dataclass(frozen=True, slots=True)
class RestUseCases:
    """WH-01 part 2: rest periods and the reminder's insert-if-absent 🧘 / 😌 (Q26)."""

    start: StartRestPeriod
    restore: RestoreRestPeriod
    end: EndRestPeriod
    log_from_reminder: LogFromReminder
    skip: SkipRestPeriod


@dataclass(frozen=True, slots=True)
class SettingsUseCases:
    profile: UpdateProfile
    settings: NotificationSettingsUseCase
    cities: Cities
    today: Callable[[Principal], tuple[date, bool]]  # GetDays.today: no DB access
    day_off: SetDayOff


@dataclass(frozen=True, slots=True)
class BotRuntime:
    bot: Bot
    dispatcher: Dispatcher


def build_runtime(
    token: str,
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
) -> BotRuntime:
    """No network: `Bot()` only validates the token format."""
    from aiogram import Bot, Dispatcher

    from tristhana.bots.telegram.router import build_router

    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(
            ensure,
            days,
            practices,
            moon,
            remind,
            settings,
            translator,
            miniapp_url,
            rest,
            check_ins,
            diary,
            progression,
        )
    )
    return BotRuntime(bot=Bot(token), dispatcher=dispatcher)


def webhook_reply(runtime: BotRuntime, method: TelegramMethod[Any]) -> dict[str, Any]:
    """The Bot API call as a webhook-reply JSON body (`{"method": ..., params...}`)."""
    body: dict[str, Any] = {"method": method.__api_method__}
    files: dict[str, Any] = {}
    for key, value in method.model_dump(warnings=False).items():
        # _dumps_json=False: native JSON values (aiogram's default stringifies for form posts);
        # bot defaults such as parse_mode are resolved here.
        prepared = runtime.bot.session.prepare_value(
            value, bot=runtime.bot, files=files, _dumps_json=False
        )
        if prepared is not None:
            body[key] = prepared
    if files:
        raise ValueError("file uploads cannot be sent as a webhook reply")
    return body
