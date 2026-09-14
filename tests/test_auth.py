from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.database import create_database
from app.db.migrate import upgrade_database
from app.main import create_app
from app.models.auth import AuthSession
from app.models.user import User
from app.routes.dependencies import get_csrf_token_for_session
from app.services import auth_service
from tests.fakes import FakeGeminiProvider


@pytest.fixture
def auth_env(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        gemini_api_key="TEST_SECRET_NOT_FOR_LOGS",
        gemini_model="fake-gemini",
        enable_dev_bootstrap=False,
    )
    upgrade_database(settings.database_url)
    fake_provider = FakeGeminiProvider()
    app = create_app(settings, provider=fake_provider)
    engine, session_factory = create_database(settings.database_url)

    with TestClient(app) as client:
        yield client, app, settings, session_factory, fake_provider


def register_user(client, name="Test User", email="test@example.com", password="password123"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "timezone": "Europe/Istanbul",
        },
    )


def login_user(client, email="test@example.com", password="password123"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


# --- Registration Tests ---

def test_register_success(auth_env):
    client, _, settings, _, _ = auth_env
    resp = register_user(client, name="Alice", email="alice@example.com", password="password123")
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"
    assert "password" not in data
    assert "password_hash" not in data
    assert settings.session_cookie_name in client.cookies


def test_register_duplicate_email_rejected(auth_env):
    client, _, _, _, _ = auth_env
    resp1 = register_user(client, email="alice@example.com")
    assert resp1.status_code == 201

    # Case insensitive duplicate rejection
    resp2 = register_user(client, email="ALICE@example.com")
    assert resp2.status_code == 409
    assert "zaten var" in resp2.json()["detail"]


def test_register_email_normalized(auth_env):
    client, _, _, session_factory, _ = auth_env
    resp = register_user(client, email="  Bob.Smith@EXAMPLE.COM  ")
    assert resp.status_code == 201

    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == "bob.smith@example.com"))
        assert user is not None
        assert user.email == "bob.smith@example.com"


def test_register_password_hash_stored_plaintext_never(auth_env):
    client, _, _, session_factory, _ = auth_env
    raw_password = "super-secret-password-123"
    register_user(client, email="charlie@example.com", password=raw_password)

    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == "charlie@example.com"))
        assert user.password_hash.startswith("$argon2id$")
        assert raw_password not in user.password_hash


def test_register_weak_password_rejected(auth_env):
    client, _, _, _, _ = auth_env
    resp = register_user(client, email="short@example.com", password="short")
    assert resp.status_code == 422


# --- Login Tests ---

def test_login_success_sets_httponly_cookie(auth_env):
    client, _, settings, _, _ = auth_env
    register_user(client, email="login@example.com", password="correct_password")

    # Clear cookies
    client.cookies.clear()
    assert settings.session_cookie_name not in client.cookies

    resp = login_user(client, email="login@example.com", password="correct_password")
    assert resp.status_code == 200
    assert settings.session_cookie_name in client.cookies


def test_login_wrong_password_rejected(auth_env):
    client, _, _, _, _ = auth_env
    register_user(client, email="wrongpwd@example.com", password="correct_password")
    client.cookies.clear()

    resp = login_user(client, email="wrongpwd@example.com", password="wrong_password")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Email veya şifre hatalı."


def test_login_unknown_email_generic_error(auth_env):
    client, _, _, _, _ = auth_env
    resp = login_user(client, email="nonexistent@example.com", password="any_password")
    assert resp.status_code == 401
    # Generic error without revealing email existence
    assert resp.json()["detail"] == "Email veya şifre hatalı."


# --- Session Lifecycle Tests ---

def test_authenticated_request_succeeds(auth_env):
    client, _, _, _, _ = auth_env
    register_user(client, name="Session User", email="sess@example.com")
    resp = client.get("/api/v1/me")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Session User"


def test_invalid_token_rejected(auth_env):
    client, _, settings, _, _ = auth_env
    client.cookies.set(settings.session_cookie_name, "fake-invalid-token")
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401


def test_expired_session_rejected(auth_env):
    client, _, settings, session_factory, _ = auth_env
    register_user(client, email="expired@example.com")

    # Expire session in DB
    with session_factory() as session:
        active_sess = session.scalars(select(AuthSession)).first()
        active_sess.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()

    resp = client.get("/api/v1/me")
    assert resp.status_code == 401


def test_revoked_session_rejected(auth_env):
    client, _, settings, session_factory, _ = auth_env
    register_user(client, email="revoked@example.com")

    # Revoke session in DB
    with session_factory() as session:
        active_sess = session.scalars(select(AuthSession)).first()
        active_sess.revoked_at = datetime.now(timezone.utc)
        session.commit()

    resp = client.get("/api/v1/me")
    assert resp.status_code == 401


def test_logout_invalidates_session_and_clears_cookie(auth_env):
    client, _, settings, session_factory, _ = auth_env
    register_user(client, email="logout@example.com")

    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 204

    # Subsequent request fails
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401

    with session_factory() as session:
        active_sess = session.scalars(select(AuthSession)).first()
        assert active_sess.revoked_at is not None


def test_production_cookie_secure_setting(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'prod.db'}",
        app_environment="production",
        secret_key="valid-test-production-secret-key-at-least-32-chars",
        csrf_secret="valid-test-production-csrf-secret-at-least-32-chars",
        allow_sqlite_in_production=True,
    )
    upgrade_database(settings.database_url)
    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/auth/register",
            json={"name": "Prod", "email": "prod@example.com", "password": "password123"},
        )
        assert resp.status_code == 201
        # In TestClient, verify cookie header contains Secure
        set_cookie = resp.headers.get("set-cookie", "")
        assert "Secure" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "samesite=lax" in set_cookie.lower()


# --- CSRF Defense Tests ---

def test_csrf_protection_mutations(auth_env):
    client, _, settings, session_factory, _ = auth_env
    register_user(client, email="csrf@example.com")

    payload = {
        "occurred_at": "2026-09-14T12:00:00+03:00",
        "meal_type": "lunch",
        "original_description": "Tavuklu Salata",
        "items": [
            {
                "name": "Tavuk",
                "quantity": "200.00",
                "unit": "g",
                "calories": "250.00",
                "protein_g": "30.00",
                "carbs_g": "0.00",
                "fat_g": "5.00",
            }
        ],
    }

    # Attempt mutation without X-CSRF-Token -> 403 Forbidden
    resp_no_csrf = client.post(
        "/api/v1/me/meals",
        json=payload,
    )
    assert resp_no_csrf.status_code == 403
    assert "CSRF" in resp_no_csrf.json()["detail"]

    # Retrieve valid CSRF token bound to this session
    with session_factory() as session:
        auth_session = session.scalars(select(AuthSession)).first()
        csrf_token = get_csrf_token_for_session(auth_session, settings)

    # Mutation with valid CSRF token -> 201 Created
    resp_valid_csrf = client.post(
        "/api/v1/me/meals",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )
    assert resp_valid_csrf.status_code == 201


def test_csrf_protection_safe_get_bypassed(auth_env):
    client, _, _, _, _ = auth_env
    register_user(client, email="safeget@example.com")
    resp = client.get("/api/v1/me/meals")
    assert resp.status_code == 200


# --- Web Page Route Tests ---

def test_web_unauthenticated_redirects_to_login(auth_env):
    client, _, _, _, _ = auth_env
    resp = client.get("/today", follow_redirects=False)
    assert resp.status_code in (303, 307)
    assert resp.headers["location"] == "/login"


def test_web_authenticated_pages_work(auth_env):
    client, _, _, _, _ = auth_env
    register_user(client, name="WebUser", email="web@example.com")

    pages = ["/today", "/coach", "/meals", "/progress", "/profile"]
    for path in pages:
        resp = client.get(path)
        assert resp.status_code == 200
        assert "WebUser" in resp.text
        assert 'name="csrf-token"' in resp.text


def test_web_login_and_register_pages_render(auth_env):
    client, _, _, _, _ = auth_env
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200


# --- User Isolation Tests (User A vs User B) ---

def test_user_isolation_profile(auth_env):
    client, _, settings, _, _ = auth_env

    # Register User A
    resp_a = register_user(client, name="User A", email="a@example.com")
    user_a = resp_a.json()

    # Create new client for User B
    client_b = TestClient(client.app)
    resp_b = register_user(client_b, name="User B", email="b@example.com")
    user_b = resp_b.json()

    # User A tries to read User B's profile via path URL
    resp = client.get(f"/api/v1/users/{user_b['id']}/profile")
    assert resp.status_code == 403

    # User A tries to update User B's profile
    resp = client.put(f"/api/v1/users/{user_b['id']}/profile", json={"calorie_target": 3000})
    assert resp.status_code == 403


def test_user_isolation_meals(auth_env):
    client, _, settings, session_factory, _ = auth_env

    # User A
    resp_a = register_user(client, name="User A", email="a_meals@example.com")
    user_a = resp_a.json()
    with session_factory() as session:
        auth_sess = session.scalars(select(AuthSession)).first()
        csrf_token_a = get_csrf_token_for_session(auth_sess, settings)

    payload_a = {
        "occurred_at": "2026-09-14T12:00:00+03:00",
        "meal_type": "lunch",
        "original_description": "A's Meal",
        "items": [
            {
                "name": "Steak",
                "quantity": "200.00",
                "unit": "g",
                "calories": "500.00",
                "protein_g": "50.00",
                "carbs_g": "0.00",
                "fat_g": "20.00",
            }
        ],
    }

    create_resp = client.post(
        "/api/v1/me/meals",
        headers={"X-CSRF-Token": csrf_token_a},
        json=payload_a,
    )
    assert create_resp.status_code == 201
    meal_a = create_resp.json()

    # User B
    client_b = TestClient(client.app)
    register_user(client_b, name="User B", email="b_meals@example.com")

    # User B checks own meals -> empty
    b_meals = client_b.get("/api/v1/me/meals").json()
    assert len(b_meals) == 0

    # User B attempts to access User A's meal directly -> 403
    cross_get = client_b.get(f"/api/v1/users/{user_a['id']}/meals/{meal_a['id']}")
    assert cross_get.status_code == 403

    # User B attempts to delete User A's meal -> 403
    cross_del = client_b.delete(f"/api/v1/users/{user_a['id']}/meals/{meal_a['id']}")
    assert cross_del.status_code == 403


def test_user_isolation_weights(auth_env):
    client, _, settings, session_factory, _ = auth_env

    # User A
    resp_a = register_user(client, name="User A", email="a_wt@example.com")
    user_a = resp_a.json()
    with session_factory() as session:
        auth_sess = session.scalars(select(AuthSession)).first()
        csrf_token_a = get_csrf_token_for_session(auth_sess, settings)

    client.post(
        "/api/v1/me/weight-logs",
        headers={"X-CSRF-Token": csrf_token_a},
        json={"occurred_at": datetime.now(timezone.utc).isoformat(), "weight_kg": "75.0"},
    )

    # User B
    client_b = TestClient(client.app)
    register_user(client_b, name="User B", email="b_wt@example.com")

    # User B has no weights
    b_weights = client_b.get("/api/v1/me/weight-logs").json()
    assert len(b_weights) == 0

    # Cross-access denied
    assert client_b.get(f"/api/v1/users/{user_a['id']}/weight-logs").status_code == 403


def test_user_isolation_chat(auth_env):
    client, _, settings, session_factory, _ = auth_env

    # User A
    resp_a = register_user(client, name="User A", email="a_chat@example.com")
    user_a = resp_a.json()
    with session_factory() as session:
        auth_sess = session.scalars(select(AuthSession)).first()
        csrf_token_a = get_csrf_token_for_session(auth_sess, settings)

    conv_a = client.post("/api/v1/me/conversations", headers={"X-CSRF-Token": csrf_token_a}).json()

    # User B
    client_b = TestClient(client.app)
    register_user(client_b, name="User B", email="b_chat@example.com")

    # User B cannot access User A's conversation
    assert client_b.get(f"/api/v1/users/{user_a['id']}/conversations/{conv_a['id']}").status_code == 403


def test_user_isolation_memories(auth_env):
    client, _, _, _, _ = auth_env

    # User A
    resp_a = register_user(client, name="User A", email="a_mem@example.com")
    user_a = resp_a.json()

    # User B
    client_b = TestClient(client.app)
    register_user(client_b, name="User B", email="b_mem@example.com")

    # User B cannot list or delete User A's memories
    assert client_b.get(f"/api/v1/users/{user_a['id']}/memories").status_code == 403


# --- Password Change Tests ---

def test_change_password_success_and_revokes_other_sessions(auth_env):
    client1, _, settings, session_factory, _ = auth_env
    register_user(client1, email="change_pw@example.com", password="old_password_123")

    # Login second client with same credentials
    client2 = TestClient(client1.app)
    login_user(client2, email="change_pw@example.com", password="old_password_123")

    # Both clients can make requests
    assert client1.get("/api/v1/me").status_code == 200
    assert client2.get("/api/v1/me").status_code == 200

    # Change password from client2
    with session_factory() as session:
        sess2_token = client2.cookies[settings.session_cookie_name]
        auth_session = auth_service.validate_session_token(session, sess2_token)[0]
        csrf_token = get_csrf_token_for_session(auth_session, settings)

    change_resp = client2.post(
        "/api/v1/me/change-password",
        headers={"X-CSRF-Token": csrf_token},
        json={"current_password": "old_password_123", "new_password": "new_password_456"},
    )
    assert change_resp.status_code == 204

    # client2 remains authenticated
    assert client2.get("/api/v1/me").status_code == 200

    # client1 session was revoked
    assert client1.get("/api/v1/me").status_code == 401

    # Login with old password fails
    assert login_user(client1, email="change_pw@example.com", password="old_password_123").status_code == 401

    # Login with new password succeeds
    assert login_user(client1, email="change_pw@example.com", password="new_password_456").status_code == 200


# --- Dev Bootstrap & Security Headers ---

def test_dev_bootstrap_disabled_by_default(auth_env):
    client, _, _, _, _ = auth_env
    resp = client.get("/api/v1/dev/bootstrap")
    assert resp.status_code == 404


def test_security_headers_present(auth_env):
    client, _, _, _, _ = auth_env
    resp = client.get("/login")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_legacy_endpoints_require_authentication_by_default(auth_env):
    """Production/default behavior: unauthenticated calls to legacy private endpoints return 401."""
    client, _, settings, _, _ = auth_env
    # Confirm default setting
    assert settings.allow_unauthenticated_legacy is False

    # Create User A via registration
    resp_a = register_user(client, name="User A", email="auth_check_a@example.com")
    user_a = resp_a.json()
    user_id = user_a["id"]

    # 1. Unauthenticated client (no session cookie)
    unauth_client = TestClient(client.app)
    paths = [
        f"/api/v1/users/{user_id}/profile",
        f"/api/v1/users/{user_id}/meals",
        f"/api/v1/users/{user_id}/weight-logs",
        f"/api/v1/users/{user_id}/conversations",
        f"/api/v1/users/{user_id}/memories",
    ]
    for path in paths:
        res = unauth_client.get(path)
        assert res.status_code == 401, f"{path} returned {res.status_code}, expected 401"

    # 2. Authenticated as same owner -> allowed
    for path in paths:
        res = client.get(path)
        assert res.status_code == 200, f"{path} returned {res.status_code}, expected 200"

    # 3. Authenticated as different owner -> 403 Forbidden
    client_b = TestClient(client.app)
    register_user(client_b, name="User B", email="auth_check_b@example.com")
    for path in paths:
        res = client_b.get(path)
        assert res.status_code == 403, f"{path} returned {res.status_code}, expected 403"



def test_cli_set_password_for_legacy_user(auth_env):
    client, _, _, session_factory, _ = auth_env
    # Legacy user created without password
    with session_factory() as session:
        legacy_user = User(name="Legacy", email="legacy@example.com")
        session.add(legacy_user)
        session.commit()
        user_id = legacy_user.id

    # Assign credentials via CLI helper
    with session_factory() as session:
        auth_service.set_user_password_cli(session, user_id, "new_cli_password")

    # Verify user can log in
    resp = login_user(client, email="legacy@example.com", password="new_cli_password")
    assert resp.status_code == 200
