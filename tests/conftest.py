import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.db.migrate import upgrade_database
from app.main import create_app


@pytest.fixture
def nutrition_app(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'nutrition.db'}")
    upgrade_database(settings.database_url)
    return create_app(settings)


@pytest.fixture
def client(nutrition_app):
    with TestClient(nutrition_app) as client:
        yield client


@pytest.fixture
def users(client):
    return [client.post('/api/v1/users', json={'name': name, 'timezone': 'Europe/Istanbul'}).json()['id'] for name in ('A', 'B')]
