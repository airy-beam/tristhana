from typing import Any

import pytest
import uvicorn

from tristhana import serve
from tristhana.settings import get_settings


def test_serve_runs_one_worker_behind_the_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def fake_run(*args: Any, **kwargs: Any) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setenv("PORT", "9000")
    get_settings.cache_clear()

    try:
        serve.main()
    finally:
        get_settings.cache_clear()

    [(args, kwargs)] = calls
    assert args == ("tristhana.main:app",)
    assert kwargs["host"] == "0.0.0.0"  # noqa: S104 - inside the container
    assert kwargs["port"] == 9000
    assert kwargs["workers"] == 1
    assert kwargs["proxy_headers"] is True
    assert kwargs["access_log"] is False
    assert kwargs["log_config"] is None
