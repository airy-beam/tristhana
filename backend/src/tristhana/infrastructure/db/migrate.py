"""`tristhana-migrate`: apply migrations (the Cloud Run Job before each deploy, ADR-0014).

DATABASE_URL (the migrate role) and optional DATABASE_CA_FILE come from the environment.
Locally: `DATABASE_URL=postgresql://... uv run tristhana-migrate`.
"""

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger(__name__)


def alembic_config(url: str, ca_file: Path | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", "tristhana.infrastructure.db:migrations")
    config.attributes["url"] = url
    config.attributes["ca_file"] = ca_file
    return config


def upgrade(url: str, ca_file: Path | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url, ca_file), revision)


def downgrade(url: str, revision: str, ca_file: Path | None = None) -> None:
    command.downgrade(alembic_config(url, ca_file), revision)


def check(url: str, ca_file: Path | None = None) -> None:
    """Raises if the tables in `tables.py` and the migrations disagree."""
    command.check(alembic_config(url, ca_file))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    ca = os.environ.get("DATABASE_CA_FILE", "").strip()
    upgrade(url, Path(ca) if ca else None)
    log.info("migrations applied")
