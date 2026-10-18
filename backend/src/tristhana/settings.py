"""Process configuration, read from the environment (and `.env` locally)."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type AppEnv = Literal["dev", "test", "prod"]
type LogFormat = Literal["json", "console"]
type TelegramMode = Literal["webhook", "polling"]

# Bot API: secret_token is 1-256 characters of A-Z, a-z, 0-9, _ and -.
_WEBHOOK_SECRET = re.compile(r"[A-Za-z0-9_-]{1,256}")

# Dev/tests only (repo checkout). An installed package can't find data/seed this way,
# so the container must set SEED_DIR=/app/data/seed (it does, in backend/Dockerfile).
_REPO_SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: AppEnv = "dev"
    log_level: str = "INFO"
    # JSON for Cloud Logging; console is easier to read locally.
    log_format: LogFormat | None = None
    port: int = 8080  # Cloud Run sets PORT
    seed_dir: Path = _REPO_SEED_DIR
    git_sha: str = "dev"  # set at image build / deploy time

    # Telegram (injected from Secret Manager in prod; backend/.env in dev).
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_mode: TelegramMode = "webhook"  # dev: "polling" with @tristhana_dev_bot

    @field_validator("telegram_bot_token", "telegram_webhook_secret", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # Strip stray whitespace (e.g. a newline from `echo`); blank means "not configured".
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def _check_telegram(self) -> Self:
        if self.telegram_mode == "polling" and self.app_env == "prod":
            raise ValueError("telegram_mode=polling is for local development only")
        secret = self.telegram_webhook_secret
        if secret is not None and not _WEBHOOK_SECRET.fullmatch(secret.get_secret_value()):
            raise ValueError("telegram_webhook_secret: 1-256 chars of A-Z a-z 0-9 _ -")
        return self

    @property
    def effective_log_format(self) -> LogFormat:
        if self.log_format is not None:
            return self.log_format
        return "console" if self.app_env == "dev" else "json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
