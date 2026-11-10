from pathlib import Path

import pytest
from pydantic import ValidationError

from tristhana.settings import AppEnv, LogFormat, Settings


@pytest.mark.parametrize(
    ("app_env", "expected"),
    [("dev", "console"), ("test", "json"), ("prod", "json")],
)
def test_log_format_defaults_by_environment(app_env: AppEnv, expected: LogFormat) -> None:
    assert Settings(app_env=app_env).effective_log_format == expected


def test_explicit_log_format_wins() -> None:
    assert Settings(app_env="prod", log_format="console").effective_log_format == "console"


def test_runtime_defaults() -> None:
    settings = Settings()

    assert settings.port == 8080
    assert settings.git_sha == "dev"
    assert (settings.seed_dir / "asanas.yaml").is_file()


def test_runtime_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("SEED_DIR", str(tmp_path))
    monkeypatch.setenv("GIT_SHA", "abc1234")

    settings = Settings()

    assert (settings.port, settings.seed_dir, settings.git_sha) == (9000, tmp_path, "abc1234")


def test_polling_is_rejected_in_prod() -> None:
    with pytest.raises(ValueError, match="local development"):
        Settings(app_env="prod", telegram_mode="polling")


def test_webhook_secret_charset() -> None:
    with pytest.raises(ValueError, match="telegram_webhook_secret"):
        Settings(telegram_webhook_secret="has spaces!")  # pyright: ignore[reportArgumentType]


def test_telegram_secrets_are_hidden() -> None:
    settings = Settings(telegram_bot_token="123:abc")  # pyright: ignore[reportArgumentType]

    assert "123:abc" not in repr(settings)


def test_empty_telegram_values_mean_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "  ")

    assert Settings().telegram_bot_token is None


def test_telegram_secrets_are_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "abc-123\n")

    secret = Settings().telegram_webhook_secret

    assert secret is not None
    assert secret.get_secret_value() == "abc-123"


def test_miniapp_url_must_be_https() -> None:
    with pytest.raises(ValueError, match="miniapp_url"):
        Settings(miniapp_url="http://tristhana.web.app")


def test_prod_refuses_the_dev_init_data_endpoint() -> None:
    with pytest.raises(ValidationError, match="dev_init_data"):
        Settings(app_env="prod", dev_init_data=True)


def test_prod_database_needs_the_ca_file() -> None:
    url = "postgresql://tristhana_app:x@pooler.example:5432/postgres"
    with pytest.raises(ValidationError, match="database_ca_file"):
        Settings(app_env="prod", database_url=url)  # pyright: ignore[reportArgumentType]

    ca = "/app/certs/ca.crt"
    with pytest.raises(ValidationError, match="field_encryption_keys"):
        Settings(app_env="prod", database_url=url, database_ca_file=ca)  # pyright: ignore[reportArgumentType]

    ok = Settings(
        app_env="prod",
        database_url=url,  # pyright: ignore[reportArgumentType]
        database_ca_file=ca,  # pyright: ignore[reportArgumentType]
        field_encryption_keys="1:" + "A" * 43 + "=",  # pyright: ignore[reportArgumentType]
    )
    assert ok.database_ca_file is not None


# ID-05 (ADR-0042): platform admins as account UUIDs in the environment.
_ADMIN_A = "0b0e7f3a-52a4-4c57-9a2d-4a3c1c0d9e11"
_ADMIN_B = "7d1f6f0c-8f6e-4a0b-b1b5-0f6f2d3c4b5a"


def test_platform_admins_default_to_none() -> None:
    assert Settings(_env_file=None).platform_admins == frozenset()  # pyright: ignore[reportCallIssue]


def test_platform_admins_parse_a_comma_separated_list() -> None:
    from uuid import UUID

    settings = Settings(_env_file=None, platform_admin_ids=f" {_ADMIN_A}, {_ADMIN_B} ,")  # pyright: ignore[reportCallIssue]
    assert settings.platform_admins == frozenset({UUID(_ADMIN_A), UUID(_ADMIN_B)})


@pytest.mark.parametrize(
    "value",
    ["123456789", "not-a-uuid", _ADMIN_A.replace("-", ""), f"{_ADMIN_A};{_ADMIN_B}"],
)
def test_platform_admins_reject_anything_but_account_uuids(value: str) -> None:
    with pytest.raises(ValueError, match="platform_admin_ids"):
        Settings(_env_file=None, platform_admin_ids=value)  # pyright: ignore[reportCallIssue]


def test_platform_admins_are_at_most_five() -> None:
    from uuid import uuid4

    six = ",".join(str(uuid4()) for _ in range(6))
    with pytest.raises(ValueError, match="at most 5"):
        Settings(_env_file=None, platform_admin_ids=six)  # pyright: ignore[reportCallIssue]
