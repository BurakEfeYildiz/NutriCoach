import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.db.migrate import upgrade_database
from app.main import create_app
from tests.fakes import FakeGeminiProvider


@pytest.fixture(autouse=True)
def no_real_google(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Testte gerçek Gemini istemcisi yasak.')
    monkeypatch.setattr('app.services.gemini_service.genai.Client', forbidden)


def assert_no_connections(app):
    assert app.state.session_factory.kw['bind'].pool.checkedout() == 0


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


@pytest.fixture
def chat_env(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'chat.db'}", gemini_api_key='TEST_SECRET_NOT_FOR_LOGS', gemini_model='fake-gemini')
    upgrade_database(settings.database_url)
    fake = FakeGeminiProvider()
    app = create_app(settings, provider=fake)
    fake.on_call = lambda *_: assert_no_connections(app)
    with TestClient(app) as client:
        users = [client.post('/api/v1/users', json={'name': name}).json()['id'] for name in ('A', 'B')]
        conversations = [client.post(f'/api/v1/users/{user}/conversations').json()['id'] for user in users]
        yield client, app, fake, users, conversations
