"""Dev only: long polling for @tristhana_dev_bot with the same handlers as the webhook."""

from tristhana.bots.telegram.runtime import BotRuntime


async def run_polling(runtime: BotRuntime) -> None:
    # A bot can't poll while a webhook is set; the dev bot never has one, but be safe.
    await runtime.bot.delete_webhook(drop_pending_updates=False)
    await runtime.dispatcher.start_polling(runtime.bot, handle_signals=False)  # pyright: ignore[reportUnknownMemberType]
