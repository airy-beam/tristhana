import pytest
from fastapi.testclient import TestClient

from tristhana.main import create_app
from tristhana.settings import Settings

ORIGIN = "https://tristhana.web.app"


def _client(origins: str = ORIGIN) -> TestClient:
    return TestClient(create_app(Settings(app_env="test", cors_origins=origins)))


def test_allowed_origin_gets_cors_headers() -> None:
    response = _client().get("/api/v1/health", headers={"Origin": ORIGIN})

    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_is_cached_for_two_hours() -> None:
    response = _client().options(
        "/api/v1/health",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-max-age"] == "7200"


def test_other_origins_get_no_cors_headers() -> None:
    response = _client().get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_is_off_by_default() -> None:
    response = _client(origins="").get("/api/v1/health", headers={"Origin": ORIGIN})

    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_list_is_parsed() -> None:
    settings = Settings(cors_origins=f" {ORIGIN} , http://localhost:5173 ")

    assert settings.cors_origin_list == [ORIGIN, "http://localhost:5173"]


@pytest.mark.parametrize("bad", ["*", "https://tristhana.web.app/", "tristhana.web.app"])
def test_cors_origins_must_be_exact(bad: str) -> None:
    with pytest.raises(ValueError, match="exact origins"):
        Settings(cors_origins=bad)
