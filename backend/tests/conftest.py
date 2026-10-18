from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tristhana.main import create_app
from tristhana.settings import Settings

# Tests never read a developer's backend/.env (it may hold a dev bot token and polling mode).
Settings.model_config["env_file"] = None


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings(app_env="test"))) as test_client:
        yield test_client
