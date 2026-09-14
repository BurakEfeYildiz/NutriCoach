"""Production readiness, configuration hardening, and cloud deployment tests."""

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from app.core.config import Settings
from app.db.database import normalize_database_url, get_engine_options
from app.main import app
from app.scripts.migrate_sqlite_to_pg import migrate_data


def test_production_settings_rejects_default_secrets():
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_environment="production",
            database_url="postgresql+psycopg2://usr:pwd@localhost:5432/nutricoach",
            secret_key="nutricoach-development-secret-change-in-production-min-32-chars",
            csrf_secret="valid-production-csrf-secret-key-at-least-32-chars-long",
        )
    assert "In production, SECRET_KEY must be set" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        Settings(
            app_environment="production",
            database_url="postgresql+psycopg2://usr:pwd@localhost:5432/nutricoach",
            secret_key="valid-production-secret-key-at-least-32-chars-long",
            csrf_secret="nutricoach-csrf-development-secret-change-in-prod-32-chars",
        )
    assert "In production, CSRF_SECRET must be set" in str(exc.value)


def test_production_settings_rejects_sqlite():
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_environment="production",
            database_url="sqlite:///./nutricoach.db",
            secret_key="valid-production-secret-key-at-least-32-chars-long",
            csrf_secret="valid-production-csrf-secret-key-at-least-32-chars-long",
        )
    assert "In production, SQLite is not supported" in str(exc.value)


def test_production_settings_rejects_insecure_flags():
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_environment="production",
            database_url="postgresql+psycopg2://usr:pwd@localhost:5432/nutricoach",
            secret_key="valid-production-secret-key-at-least-32-chars-long",
            csrf_secret="valid-production-csrf-secret-key-at-least-32-chars-long",
            enable_dev_bootstrap=True,
        )
    assert "enable_dev_bootstrap must be False" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        Settings(
            app_environment="production",
            database_url="postgresql+psycopg2://usr:pwd@localhost:5432/nutricoach",
            secret_key="valid-production-secret-key-at-least-32-chars-long",
            csrf_secret="valid-production-csrf-secret-key-at-least-32-chars-long",
            allow_unauthenticated_legacy=True,
        )
    assert "allow_unauthenticated_legacy must be False" in str(exc.value)


def test_production_cookie_security_flag():
    dev_settings = Settings(app_environment="development")
    assert dev_settings.is_cookie_secure is False

    prod_settings = Settings(
        app_environment="production",
        database_url="postgresql+psycopg2://usr:pwd@localhost:5432/nutricoach",
        secret_key="valid-production-secret-key-at-least-32-chars-long",
        csrf_secret="valid-production-csrf-secret-key-at-least-32-chars-long",
        cookie_secure=False,  # Should be overridden by is_cookie_secure property in production
    )
    assert prod_settings.is_cookie_secure is True


def test_database_url_normalization():
    assert normalize_database_url("postgres://u:p@h:5432/d") == "postgresql+psycopg2://u:p@h:5432/d"
    assert normalize_database_url("postgresql://u:p@h:5432/d") == "postgresql+psycopg2://u:p@h:5432/d"
    assert normalize_database_url("postgresql+psycopg2://u:p@h:5432/d") == "postgresql+psycopg2://u:p@h:5432/d"
    assert normalize_database_url("sqlite:///./local.db") == "sqlite:///./local.db"


def test_postgresql_engine_pool_options():
    pg_opts = get_engine_options("postgresql+psycopg2://u:p@h:5432/d")
    assert pg_opts["pool_pre_ping"] is True
    assert pg_opts["pool_size"] == 5
    assert pg_opts["max_overflow"] == 10
    assert pg_opts["pool_recycle"] == 1800


def test_auth_rate_limiting():
    if hasattr(app.state, "auth_request_history"):
        app.state.auth_request_history.clear()

    client = TestClient(app)

    # 10 attempts should pass (resulting in 400, 401, or 422, not 429)
    for i in range(10):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": f"attacker_{i}@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code in (400, 401, 422)

    # 11th attempt from same IP must be rejected with 429 Too Many Requests
    resp_rate_limited = client.post(
        "/api/v1/auth/login",
        json={"email": "attacker_11@example.com", "password": "wrongpassword"},
    )
    assert resp_rate_limited.status_code == 429
    assert "Çok fazla deneme yapıldı" in resp_rate_limited.json()["detail"]

    if hasattr(app.state, "auth_request_history"):
        app.state.auth_request_history.clear()


def test_migrate_script_dry_run():
    # Calling migrate_data in dry_run mode on local sqlite database
    # ensures it connects, reads counts, and exits safely without modifying target
    stats = migrate_data(sqlite_url="sqlite:///./nutricoach.db", pg_url="sqlite:///./nutricoach.db", dry_run=True)
    assert isinstance(stats, dict)
    assert "users" in stats
