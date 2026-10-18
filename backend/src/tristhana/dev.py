"""`tristhana-dev`: run the app locally with auto-reload on :8000.

The Telegram bot (polling mode) joins here once the bot adapter exists.
"""


def main() -> None:
    import uvicorn  # imported lazily: only the dev entry point needs it

    uvicorn.run("tristhana.main:app", host="127.0.0.1", port=8000, reload=True, log_config=None)
