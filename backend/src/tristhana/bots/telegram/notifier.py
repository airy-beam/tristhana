"""`Notifier` over Telegram (ADR-0018): renders a reminder and sends it as a new message.
aiogram is imported on first use, so importing the app stays light."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.application.ports.notifications import (
    DeliveryResult,
    DeliveryStatus,
    ExportFile,
    MoonReminder,
    Notification,
    Recipient,
)

if TYPE_CHECKING:
    from tristhana.bots.telegram.runtime import BotRuntime

log = logging.getLogger(__name__)

SEND_TIMEOUT_S = 10
UPLOAD_TIMEOUT_S = 40  # the ST-09 export: up to 45 MB, within Cloud Run's 60 s request
_GONE = ("chat not found", "user is deactivated", "bot was blocked")


class TelegramNotifier:
    def __init__(self, runtime: Callable[[], BotRuntime], translator: Translator) -> None:
        self._runtime = runtime
        self._t = translator

    async def deliver(self, recipient: Recipient, notification: Notification) -> DeliveryResult:
        from tristhana.bots.telegram import moon, remind

        if isinstance(notification, MoonReminder):
            screen = moon.reminder_screen(self._t, recipient.locale, notification)
        else:
            screen = remind.reminder_screen(self._t, recipient.locale, notification)
        return await _sent(
            self._runtime().bot.send_message(
                chat_id=int(recipient.telegram_id),
                text=screen.text,
                reply_markup=screen.markup,
                request_timeout=SEND_TIMEOUT_S,  # a stalled Telegram must not eat the tick
            ),
            "reminder",
        )

    async def send_export(self, recipient: Recipient, file: ExportFile) -> DeliveryResult:
        """ST-09: a direct `sendDocument` (a webhook reply can't carry a file, ADR-0012)."""
        from aiogram.types import BufferedInputFile

        caption = self._t.t(
            recipient.locale, "export-caption", date=DateArg(file.local_date, with_year=True)
        )
        return await _sent(
            self._runtime().bot.send_document(
                chat_id=int(recipient.telegram_id),
                document=BufferedInputFile(file.content, filename=file.name),
                caption=caption,
                request_timeout=UPLOAD_TIMEOUT_S,
            ),
            "export",
        )


async def _sent(call: Awaitable[object], what: str) -> DeliveryResult:
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

    try:
        await call
    except TelegramForbiddenError:
        return DeliveryResult(DeliveryStatus.BLOCKED)
    except TelegramRetryAfter as e:
        return DeliveryResult(DeliveryStatus.RETRY_AFTER, float(e.retry_after))
    except TelegramBadRequest as e:
        if any(gone in str(e.message).lower() for gone in _GONE):
            return DeliveryResult(DeliveryStatus.BLOCKED)
        log.warning("%s rejected by Telegram: %s", what, type(e).__name__)
        return DeliveryResult(DeliveryStatus.FAILED)
    except Exception as e:  # network and the like: a later tick retries
        log.warning("%s delivery failed: %s", what, type(e).__name__)
        return DeliveryResult(DeliveryStatus.FAILED)
    return DeliveryResult(DeliveryStatus.SENT)
