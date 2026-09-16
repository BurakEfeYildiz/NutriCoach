"""Production readiness, configuration hardening, and cloud deployment tests."""

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from app.core.config import Settings
from app.db.database import normalize_database_url, get_engine_options
from app.main import app
from app.db.migrate import upgrade_database
from app.db.database import create_database
from app.scripts.migrate_sqlite_to_pg import migrate_data, normalize_source_row


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
    app.state.auth_rate_limit_enabled = True
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
    app.state.auth_rate_limit_enabled = False


def test_migrate_script_dry_run(tmp_path):
    path = tmp_path / "source.db"
    url = f"sqlite:///{path}"
    upgrade_database(url)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO users (id, name, email, timezone, created_at) VALUES ('qa-user', 'QA', 'qa@example.com', 'Europe/Istanbul', '2026-09-01 00:00:00')")
    before = path.read_bytes()
    stats = migrate_data(sqlite_url=url, pg_url=url, dry_run=True)
    assert isinstance(stats, dict)
    assert stats["users"] == 1
    assert path.read_bytes() == before


def test_pg_transfer_normalizes_sqlite_amounts_and_utc_times():
    engine, _ = create_database("sqlite:///:memory:")
    try:
        item = normalize_source_row("meal_items", {"quantity": 15000, "calories": 25000, "protein_g": 3500}, engine.dialect)
        assert item == {"quantity": Decimal("150.00"), "calories": Decimal("250.00"), "protein_g": Decimal("35.00")}
        weight = normalize_source_row("weight_logs", {"weight_kg": 7180, "occurred_at": datetime(2026, 9, 1, 22, 30)}, engine.dialect)
        assert weight["weight_kg"] == Decimal("71.80")
        assert weight["occurred_at"] == datetime(2026, 9, 1, 22, 30, tzinfo=timezone.utc)
    finally:
        engine.dispose()
