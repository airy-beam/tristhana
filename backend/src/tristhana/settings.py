"""Process configuration, read from the environment (and `.env` locally)."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type AppEnv = Literal["dev", "test", "prod"]
type LogFormat = Literal["json", "console"]
type TelegramMode = Literal["webhook", "polling"]

# Bot API: secret_token is 1-256 characters of A-Z, a-z, 0-9, _ and -.
_WEBHOOK_SECRET = re.compile(r"[A-Za-z0-9_-]{1,256}")
_MAX_ADMINS = 5

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

    # Mini App URL for the /start button and the menu button (empty = no button). Telegram
    # only opens HTTPS web apps.
    miniapp_url: str = ""
    # SC-06: the public https base of this API, for calendar feed links (empty: the feature is
    # hidden). Published links depend on it: keep the host serving /ical/v1 once it's used.
    public_api_url: str = ""

    # Exact browser origins allowed to call the API (comma-separated; empty = CORS off).
    cors_origins: str = ""

    # Telegram (injected from Secret Manager in prod; backend/.env in dev).
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_bot_username: str = ""
    telegram_mode: TelegramMode = "webhook"  # dev: "polling" with @tristhana_dev_bot

    # Postgres (ADR-0014). Unset: the app starts, DB features answer "temporarily unavailable".
    database_url: SecretStr | None = None
    # Supabase's CA certificate: TLS verify-full when set (prod); local Postgres runs without.
    database_ca_file: Path | None = None
    db_pool_size: int = 3
    db_max_overflow: int = 2

    # Field-level encryption keyring (ADR-0016): "<id>:<base64 32 bytes>[,…]", first = active.
    # Unset: private values (ladies' holiday) are unavailable, never stored in plain text.
    field_encryption_keys: SecretStr | None = None

    # Shared secret for POST /internal/tick (Cloud Scheduler sends it as a header, ADR-0018).
    # Unset: the tick endpoint isn't mounted.
    internal_tick_token: SecretStr | None = None

    # ID-05 (ADR-0042): platform admins, as comma-separated account UUIDs (not Telegram ids;
    # not a secret). Empty: the directory listing feature is off. They answer directory
    # requests in the bot (/admin) and can do nothing else.
    platform_admin_ids: str = ""

    # Dev only: GET /dev/telegram-init-data signs initData for ANY user id with the bot token,
    # for the Mini App's browser mock. Explicit opt-in on top of APP_ENV=dev; refused in prod.
    dev_init_data: bool = False

    @field_validator("miniapp_url")
    @classmethod
    def _https_only(cls, value: str) -> str:
        if value and not value.startswith("https://"):
            raise ValueError("miniapp_url must be an https:// URL (Telegram requirement)")
        return value

    @field_validator("public_api_url")
    @classmethod
    def _public_https(cls, value: str) -> str:
        if value and not value.startswith("https://"):
            raise ValueError("public_api_url must be an https:// URL (calendar feed links)")
        return value.rstrip("/")

    @field_validator("cors_origins")
    @classmethod
    def _exact_origins(cls, value: str) -> str:
        for origin in (o.strip() for o in value.split(",") if o.strip()):
            if origin == "*" or origin.endswith("/") or "://" not in origin:
                raise ValueError(
                    f"cors_origins: exact origins like https://x.web.app, got {origin!r}"
                )
        return value

    @field_validator("platform_admin_ids")
    @classmethod
    def _admin_uuids(cls, value: str) -> str:
        ids = [i.strip() for i in value.split(",") if i.strip()]
        for i in ids:
            try:
                parsed = UUID(i)
            except ValueError:
                raise ValueError("platform_admin_ids: comma-separated account UUIDs") from None
            if str(parsed) != i.lower():
                raise ValueError("platform_admin_ids: comma-separated account UUIDs")
        if len(ids) > _MAX_ADMINS:
            raise ValueError(f"platform_admin_ids: at most {_MAX_ADMINS}")
        return value

    @property
    def platform_admins(self) -> frozenset[UUID]:
        return frozenset(UUID(i.strip()) for i in self.platform_admin_ids.split(",") if i.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator(
        "telegram_bot_token",
        "telegram_webhook_secret",
        "database_url",
        "field_encryption_keys",
        "internal_tick_token",
        mode="before",
    )
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # Strip stray whitespace (e.g. a newline from `echo`); blank means "not configured".
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("database_ca_file", mode="before")
    @classmethod
    def _blank_path_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _check_telegram(self) -> Self:
        if self.telegram_mode == "polling" and self.app_env == "prod":
            raise ValueError("telegram_mode=polling is for local development only")
        if self.app_env == "prod" and self.dev_init_data:
            raise ValueError("dev_init_data is for local development only")
        if self.app_env == "prod" and self.database_url and self.database_ca_file is None:
            raise ValueError("database_ca_file is required in prod (TLS verify-full, ADR-0014)")
        if self.app_env == "prod" and self.database_url and self.field_encryption_keys is None:
            raise ValueError("field_encryption_keys is required in prod with a database (ADR-0016)")
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
