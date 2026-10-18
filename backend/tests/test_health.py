from fastapi.testclient import TestClient

from tristhana import __version__
from tristhana.main import create_app
from tristhana.settings import Settings


def test_health_reports_ok_and_version(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_openapi_schema_lists_health(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]


def test_interactive_docs_hidden_in_prod() -> None:
    with TestClient(create_app(Settings(app_env="prod"))) as prod_client:
        assert prod_client.get("/docs").status_code == 404
        assert prod_client.get("/openapi.json").status_code == 200
