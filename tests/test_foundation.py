import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.main import create_app
from app.db.migrate import upgrade_database


@pytest.fixture
def settings(tmp_path):
    config = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    upgrade_database(config.database_url)
    return config


def test_persistence_and_profile_isolation(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get('/health').json() == {'status': 'ok', 'database': 'ok'}
        response = client.post('/api/v1/users', json={'name': 'Birinci'})
        assert response.status_code == 201
        first = response.json()['id']
        second = client.post('/api/v1/users', json={'name': 'İkinci'}).json()['id']
        updated = client.put(f'/api/v1/users/{first}/profile', json={'calorie_target': 2200, 'protein_target_g': 150})
        assert updated.status_code == 200
        assert updated.json()['user_id'] == first
        assert client.get(f'/api/v1/users/{second}/profile').json()['calorie_target'] is None
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f'/api/v1/users/{first}').json()['name'] == 'Birinci'
        assert restarted.get(f'/api/v1/users/{first}/profile').json()['calorie_target'] == 2200
        assert restarted.get(f'/api/v1/users/{first}/profile').json()['updated_at'].endswith('Z')


def test_validation_and_conflicts(settings):
    with TestClient(create_app(settings)) as client:
        for data in [{'name': '   '}, {'name': 'A', 'timezone': 'Invalid/Zone'}, {'name': 'A', 'email': 'invalid'}, {'name': 'A', 'user_id': 'fake'}]:
            assert client.post('/api/v1/users', json=data).status_code == 422
        data = {'name': 'A', 'email': 'user@example.com'}
        user_id = client.post('/api/v1/users', json=data).json()['id']
        assert client.post('/api/v1/users', json=data).status_code == 409
        for profile in [{'calorie_target': -1}, {'height_cm': 0}, {'birth_date': '2999-01-01'}, {'protein_target_g': -10}]:
            assert client.put(f'/api/v1/users/{user_id}/profile', json=profile).status_code == 422
        assert client.get('/api/v1/users/00000000-0000-0000-0000-000000000000/profile').status_code == 404
        assert client.get('/api/v1/users/not-a-uuid').status_code == 422


def test_foreign_keys_and_db_constraints(settings):
    application = create_app(settings)
    with TestClient(application):
        with application.state.session_factory() as session:
            assert session.execute(text('PRAGMA foreign_keys')).scalar() == 1
            with pytest.raises(IntegrityError):
                session.execute(text("INSERT INTO user_profiles (user_id, updated_at) VALUES ('missing', CURRENT_TIMESTAMP)"))
            session.rollback()
            session.execute(text("INSERT INTO users (id, name, timezone, created_at) VALUES ('valid', 'Test', 'UTC', CURRENT_TIMESTAMP)"))
            session.commit()
            with pytest.raises(IntegrityError):
                session.execute(text("INSERT INTO user_profiles (user_id, calorie_target, updated_at) VALUES ('valid', -1, CURRENT_TIMESTAMP)"))
            session.rollback()


def test_put_replaces_profile(settings):
    with TestClient(create_app(settings)) as client:
        user_id = client.post('/api/v1/users', json={'name': 'Test'}).json()['id']
        url = f'/api/v1/users/{user_id}/profile'
        client.put(url, json={'calorie_target': 2200, 'protein_target_g': 150})
        result = client.put(url, json={'calorie_target': 2100})
        assert result.json()['protein_target_g'] is None
        assert result.json()['calorie_target'] == 2100
