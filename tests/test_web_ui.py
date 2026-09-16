from fastapi.testclient import TestClient
import pytest
import re

from app.core.config import Settings
from app.db.migrate import upgrade_database
from app.main import create_app
from tests.fakes import FakeGeminiProvider


@pytest.fixture
def web_client(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        gemini_api_key="TEST_KEY_NEVER_LEAK",
        gemini_model="fake-gemini",
        enable_dev_bootstrap=True,
    )
    upgrade_database(settings.database_url)
    app = create_app(settings, provider=FakeGeminiProvider())
    with TestClient(app) as client:
        yield client


@pytest.fixture
def authenticated_web_client(web_client):
    reg = web_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Web Test User",
            "email": "webuser@example.com",
            "password": "password123",
            "timezone": "Europe/Istanbul",
        },
    )
    assert reg.status_code == 201
    page = web_client.get("/onboarding")
    csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text).group(1)
    completed = web_client.put(
        "/api/v1/me/onboarding",
        headers={"X-CSRF-Token": csrf},
        json={
            "birth_date": "1990-01-01", "biological_sex": "male", "height_cm": "180",
            "current_weight_kg": "80", "target_weight_kg": "75", "goal_type": "lose",
            "activity_level": "moderate", "training_frequency": "three_four",
            "pace_percent_per_week": "0.50", "pregnancy_or_breastfeeding": False,
        },
    )
    assert completed.status_code == 200
    return web_client


def test_root_unauthenticated_redirects_to_login(web_client):
    response = web_client.get("/", follow_redirects=False)
    assert response.status_code in (307, 303, 302, 301)
    assert response.headers["location"] == "/login"


def test_root_authenticated_redirects_to_today(authenticated_web_client):
    response = authenticated_web_client.get("/", follow_redirects=False)
    assert response.status_code in (307, 303, 302, 301)
    assert response.headers["location"] == "/today"


def test_pages_return_200_html(authenticated_web_client, web_client):
    pages = [
        ("/today", "Bugün"),
        ("/coach", "Koç"),
        ("/meals", "Öğünler"),
        ("/progress", "İlerleme"),
        ("/profile", "Beslenme planım"),
        ("/account", "Hesabım"),
    ]
    for path, expected_text in pages:
        resp = authenticated_web_client.get(path, follow_redirects=True)
        assert resp.status_code == 200, f"{path} failed with {resp.status_code}"
        assert "text/html" in resp.headers["content-type"]
        assert expected_text in resp.text
        assert "NutriCoach" in resp.text

    unauth_client = TestClient(authenticated_web_client.app)
    guest_pages = [
        ("/login", "Giriş Yap"),
        ("/register", "Kayıt Ol"),
    ]
    for path, expected_text in guest_pages:
        resp = unauth_client.get(path, follow_redirects=True)
        assert resp.status_code == 200, f"{path} failed with {resp.status_code}"
        assert "text/html" in resp.headers["content-type"]
        assert expected_text in resp.text
        assert "NutriCoach" in resp.text


def test_static_assets_resolve(web_client):
    assets = [
        ("/static/css/app.css", "text/css"),
        ("/static/js/api.js", "javascript"),
        ("/static/js/ui.js", "javascript"),
        ("/static/js/dashboard.js", "javascript"),
        ("/static/js/coach.js", "javascript"),
        ("/static/js/meals.js", "javascript"),
        ("/static/js/progress.js", "javascript"),
        ("/static/js/profile.js", "javascript"),
        ("/static/js/account.js", "javascript"),
        ("/static/js/onboarding.js", "javascript"),
    ]
    for path, expected_mime in assets:
        resp = web_client.get(path)
        assert resp.status_code == 200, f"{path} failed with {resp.status_code}"
        assert expected_mime in resp.headers["content-type"]
        assert len(resp.content) > 20


def test_no_secrets_in_rendered_html(authenticated_web_client):
    pages = ["/today", "/coach", "/meals", "/progress", "/profile"]
    for path in pages:
        resp = authenticated_web_client.get(path)
        assert "TEST_KEY_NEVER_LEAK" not in resp.text
        assert "gemini_api_key" not in resp.text.lower()
        assert "secret" not in resp.text.lower()


def test_dev_bootstrap_and_users_list(web_client):
    # Call dev bootstrap -> provisions or returns user
    resp = web_client.get("/api/v1/dev/bootstrap")
    assert resp.status_code == 200
    user_data = resp.json()
    assert "id" in user_data
    assert user_data["name"] == "Burak"
    assert user_data["timezone"] == "Europe/Istanbul"

    # Subsequent call returns same user
    resp2 = web_client.get("/api/v1/dev/bootstrap")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == user_data["id"]

    # List users endpoint includes provisioned user
    users_resp = web_client.get("/api/v1/users")
    assert users_resp.status_code == 200
    user_ids = [u["id"] for u in users_resp.json()]
    assert user_data["id"] in user_ids
