import pytest

from tristhana.settings import AppEnv, LogFormat, Settings


@pytest.mark.parametrize(
    ("app_env", "expected"),
    [("dev", "console"), ("test", "json"), ("prod", "json")],
)
def test_log_format_defaults_by_environment(app_env: AppEnv, expected: LogFormat) -> None:
    assert Settings(app_env=app_env).effective_log_format == expected


def test_explicit_log_format_wins() -> None:
    assert Settings(app_env="prod", log_format="console").effective_log_format == "console"
