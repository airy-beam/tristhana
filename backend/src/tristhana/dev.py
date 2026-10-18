"""`tristhana-dev`: run the app locally with auto-reload on :8000.

With TELEGRAM_MODE=polling and the @tristhana_dev_bot token in backend/.env, the bot runs
long polling inside the same process (see backend/.env.example).
"""


def main() -> None:
    import uvicorn  # imported lazily: only the dev entry point needs it

    uvicorn.run("tristhana.main:app", host="127.0.0.1", port=8000, reload=True, log_config=None)
