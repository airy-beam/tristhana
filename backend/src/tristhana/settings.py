"""Process configuration, read from the environment (and `.env` locally)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

type AppEnv = Literal["dev", "test", "prod"]
type LogFormat = Literal["json", "console"]

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

    @property
    def effective_log_format(self) -> LogFormat:
        if self.log_format is not None:
            return self.log_format
        return "console" if self.app_env == "dev" else "json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
