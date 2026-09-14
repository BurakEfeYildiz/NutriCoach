import importlib.util
import sqlite3

import pytest
from alembic import command
from sqlalchemy import inspect, text
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.database import create_database
from app.db.migrate import ROOT, migration_config, upgrade_database
from app.main import create_app


def phase1_metadata():
    spec = importlib.util.spec_from_file_location('baseline', ROOT / 'migrations/versions/0001_foundation.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.foundation_metadata()


def test_adopts_phase1_preserves_file_and_rows(tmp_path):
    path = tmp_path / 'legacy.db'
    url = f'sqlite:///{path}'
    engine, _ = create_database(url)
    phase1_metadata().create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, name, email, timezone, created_at) VALUES ('old-user', 'Eski Kullanıcı', 'legacy@example.com', 'Europe/Istanbul', '2026-09-01 00:00:00')"))
        connection.execute(text("INSERT INTO user_profiles (user_id, height_cm, calorie_target, protein_target_g, updated_at) VALUES ('old-user', 180.5, 2200, 150.5, '2026-09-01 00:00:00')"))
    engine.dispose()
    inode = path.stat().st_ino
    with sqlite3.connect(path) as connection:
        before = {name: connection.execute(f'SELECT * FROM {name}').fetchall() for name in ('users', 'user_profiles')}
    backup = upgrade_database(url)
    assert path.exists() and path.stat().st_ino == inode
    assert backup.exists()
    for filename in (path, backup):
        with sqlite3.connect(filename) as connection:
            assert {name: connection.execute(f'SELECT * FROM {name}').fetchall() for name in before} == before
    upgrade_database(url)  # Re-running is safe.
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone() == ('0004',)
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert connection.execute('SELECT calorie_target FROM user_profiles').fetchone() == (2200,)
    with TestClient(create_app(Settings(_env_file=None, database_url=url))) as client:
        assert client.get('/health').status_code == 200


def test_fresh_database_and_metadata_match(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    assert upgrade_database(url) is None
    engine, _ = create_database(url)
    with engine.begin() as connection:
        config = migration_config(); config.attributes['connection'] = connection
        command.check(config)
        assert {'users', 'user_profiles', 'meals', 'meal_items', 'weight_logs', 'conversations', 'messages', 'ai_requests', 'memories', 'alembic_version'} == set(inspect(connection).get_table_names())
    engine.dispose()


def test_unknown_schema_not_adopted_or_deleted(tmp_path):
    path = tmp_path / 'unknown.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE precious (value TEXT)')
        connection.execute("INSERT INTO precious VALUES ('keep me')")
    with pytest.raises(RuntimeError, match='şema'):
        upgrade_database(f'sqlite:///{path}')
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT value FROM precious').fetchone() == ('keep me',)
        assert connection.execute('SELECT * FROM alembic_version').fetchall() == []


def test_app_requires_explicit_migration(tmp_path):
    app = create_app(Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'empty.db'}"))
    with pytest.raises(RuntimeError, match='migrate'):
        with TestClient(app):
            pass


def test_phase2_to_chat_preserves_all_nutrition_rows(tmp_path):
    from datetime import datetime, timezone
    from app.models.user import User, UserProfile
    from app.schemas.nutrition import MealWrite, WeightWrite
    from app.services.nutrition import create_meal
    from app.services.weights import create_weight
    from tests.test_nutrition import meal_payload

    path = tmp_path / 'phase2.db'
    url = f'sqlite:///{path}'
    engine, sessions = create_database(url)
    with engine.begin() as connection:
        config = migration_config(); config.attributes['connection'] = connection
        command.upgrade(config, '0002')
    with sessions() as session:
        user = User(name='Migration demo', profile=UserProfile(calorie_target=2200))
        session.add(user); session.commit()
        create_meal(session, user.id, MealWrite.model_validate(meal_payload()))
        create_weight(session, user.id, WeightWrite(occurred_at=datetime.now(timezone.utc), weight_kg='97.80'))
    engine.dispose()
    tables = ('users', 'user_profiles', 'meals', 'meal_items', 'weight_logs')
    with sqlite3.connect(path) as connection:
        before = {table: connection.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall() for table in tables}
    inode = path.stat().st_ino
    backup = upgrade_database(url)
    assert path.stat().st_ino == inode
    for filename in (path, backup):
        with sqlite3.connect(filename) as connection:
            assert {table: connection.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall() for table in tables} == before
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone() == ('0004',)
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_migration_0004_upgrade_and_downgrade(tmp_path):
    path = tmp_path / 'mig0004.db'
    url = f'sqlite:///{path}'
    engine, _ = create_database(url)
    with engine.begin() as connection:
        config = migration_config()
        config.attributes['connection'] = connection
        command.upgrade(config, '0003')

    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone() == ('0003',)
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert 'memories' not in tables

    with engine.begin() as connection:
        config = migration_config()
        config.attributes['connection'] = connection
        command.upgrade(config, '0004')

    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone() == ('0004',)
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert 'memories' in tables

    with engine.begin() as connection:
        config = migration_config()
        config.attributes['connection'] = connection
        command.downgrade(config, '0003')

    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone() == ('0003',)
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert 'memories' not in tables

    with engine.begin() as connection:
        config = migration_config()
        config.attributes['connection'] = connection
        command.upgrade(config, '0004')

    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone() == ('0004',)
    engine.dispose()
