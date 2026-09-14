import io
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.database import create_database
from app.db.migrate import upgrade_database
from app.main import create_app
from app.models.auth import AuthSession
from app.models.nutrition import Meal, MealItem
from app.routes.dependencies import get_csrf_token_for_session
from app.services import auth_service
from app.services.chat_service import should_use_search
from tests.fakes import FakeGeminiProvider


@pytest.fixture
def smart_inputs_env(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'smart_inputs.db'}",
        gemini_api_key="TEST_SECRET_KEY",
        gemini_model="fake-gemini",
        enable_dev_bootstrap=False,
    )
    upgrade_database(settings.database_url)
    fake_provider = FakeGeminiProvider()
    app = create_app(settings, provider=fake_provider)
    _, session_factory = create_database(settings.database_url)

    with TestClient(app) as client:
        yield client, app, settings, session_factory, fake_provider


def register_user(client, name="Test User", email="user@example.com", password="password123"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "timezone": "Europe/Istanbul",
        },
    )


def get_csrf(client, session_factory, settings):
    cookie_val = client.cookies.get(settings.session_cookie_name)
    if not cookie_val:
        return ""
    token_hash = auth_service.hash_token(cookie_val)
    with session_factory() as session:
        auth_session = session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
        if auth_session:
            return get_csrf_token_for_session(auth_session, settings)
    return ""


def make_test_image(format="JPEG", size=(200, 200), color=(100, 200, 50)):
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format)
    return buf.getvalue()


# ==============================================================================
# ==============================================================================
# Feature A: Meal Photo Analysis Tests
# ==============================================================================

def test_photo_analysis_requires_authentication(smart_inputs_env):
    client, _, _, _, _ = smart_inputs_env
    # Unauthenticated request
    img_bytes = make_test_image()
    resp = client.post(
        "/api/v1/me/meals/analyze-photo",
        files={"file": ("meal.jpg", img_bytes, "image/jpeg")},
    )
    assert resp.status_code == 401


def test_photo_analysis_valid_jpeg_success(smart_inputs_env):
    client, _, settings, session_factory, fake_provider = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    img_bytes = make_test_image(format="JPEG")
    resp = client.post(
        "/api/v1/me/meals/analyze-photo",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("lunch.jpg", img_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Izgara Tavuk"
    assert float(data["items"][0]["calories"]) == 300.0
    assert data["meal_type"] == "lunch"
    assert float(data["confidence"]) == 0.85


def test_photo_analysis_valid_png_success(smart_inputs_env):
    client, _, settings, session_factory, _ = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    img_bytes = make_test_image(format="PNG")
    resp = client.post(
        "/api/v1/me/meals/analyze-photo",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("salad.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 1


def test_photo_analysis_invalid_mime_type_rejected(smart_inputs_env):
    client, _, settings, session_factory, _ = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    resp = client.post(
        "/api/v1/me/meals/analyze-photo",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("recipe.txt", b"Hello text", "text/plain")},
    )
    assert resp.status_code == 400
    assert "Desteklenmeyen dosya türü" in resp.json()["detail"]


def test_photo_analysis_oversized_rejected(smart_inputs_env):
    client, _, settings, session_factory, _ = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    # Fake oversized content (10MB + 10 bytes)
    big_file = b"X" * (10 * 1024 * 1024 + 10)
    resp = client.post(
        "/api/v1/me/meals/analyze-photo",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("big.jpg", big_file, "image/jpeg")},
    )
    assert resp.status_code == 413
    assert "10 MB" in resp.json()["detail"]


def test_photo_analysis_corrupted_image_rejected(smart_inputs_env):
    client, _, settings, session_factory, _ = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    # Claims to be JPEG, but contains corrupt bytes
    corrupt_bytes = b"NOT_A_VALID_IMAGE_DATA_12345"
    resp = client.post(
        "/api/v1/me/meals/analyze-photo",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("corrupt.jpg", corrupt_bytes, "image/jpeg")},
    )
    assert resp.status_code == 400
    assert "Geçersiz veya bozuk görsel dosyası" in resp.json()["detail"]


def test_photo_analysis_creates_no_database_records(smart_inputs_env):
    client, _, settings, session_factory, _ = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    img_bytes = make_test_image()
    resp = client.post(
        "/api/v1/me/meals/analyze-photo",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("meal.jpg", img_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200

    # Verify zero meal records created in database
    with session_factory() as db:
        meals_count = db.query(Meal).count()
        items_count = db.query(MealItem).count()
        assert meals_count == 0
        assert items_count == 0


def test_photo_confirmation_creates_exact_meal(smart_inputs_env):
    from datetime import datetime, timezone
    client, _, settings, session_factory, _ = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    # Step 1: Analyze photo
    img_bytes = make_test_image()
    resp = client.post(
        "/api/v1/me/meals/analyze-photo",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("meal.jpg", img_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200
    analysis = resp.json()

    # Step 2: Edit or accept proposal and save
    items_to_save = analysis["items"]
    items_to_save[0]["quantity"] = 1.5
    items_to_save[0]["calories"] = 330

    create_resp = client.post(
        "/api/v1/me/meals",
        headers={"X-CSRF-Token": csrf},
        json={
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "meal_type": analysis["meal_type"],
            "original_description": "Izgara Tavuk Öğünü",
            "nutrition_source": "estimate",
            "items": [
                {
                    "name": it["name"],
                    "quantity": it["quantity"],
                    "unit": it["unit"],
                    "calories": it["calories"],
                    "protein_g": it["protein_g"],
                    "carbs_g": it["carbs_g"],
                    "fat_g": it["fat_g"],
                    "source": "estimate",
                }
                for it in items_to_save
            ],
        },
    )
    assert create_resp.status_code == 201

    # Verify database state
    with session_factory() as db:
        assert db.query(Meal).count() == 1
        saved_meal = db.query(Meal).first()
        assert len(saved_meal.items) == 1
        assert saved_meal.items[0].calories == 330


def test_zero_image_storage_in_db_schema(smart_inputs_env):
    client, _, _, session_factory, _ = smart_inputs_env
    with session_factory() as db:
        meal_cols = [c.name for c in Meal.__table__.columns]
        item_cols = [c.name for c in MealItem.__table__.columns]

        assert "image" not in meal_cols
        assert "photo" not in meal_cols
        assert "image_data" not in meal_cols
        assert "image" not in item_cols


def test_cross_user_isolation(smart_inputs_env):
    from datetime import datetime, timezone
    client, _, settings, session_factory, _ = smart_inputs_env
    # User A registers and creates a meal from photo
    reg_a = register_user(client, name="Alice", email="alice@test.com")
    assert reg_a.status_code == 201
    csrf_a = get_csrf(client, session_factory, settings)

    meal_a_resp = client.post(
        "/api/v1/me/meals",
        headers={"X-CSRF-Token": csrf_a},
        json={
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "meal_type": "lunch",
            "original_description": "Alice's Salad",
            "nutrition_source": "estimate",
            "items": [{"name": "Salad", "quantity": 1, "unit": "bowl", "calories": 150, "protein_g": 3, "carbs_g": 10, "fat_g": 5, "source": "estimate"}],
        },
    )
    assert meal_a_resp.status_code == 201
    meal_a = meal_a_resp.json()

    # User B registers (client cookies updated to User B session)
    reg_b = register_user(client, name="Bob", email="bob@test.com")
    assert reg_b.status_code == 201
    csrf_b = get_csrf(client, session_factory, settings)

    # User B lists today's meals -> empty
    b_meals = client.get("/api/v1/me/meals").json()
    assert len(b_meals) == 0

    # User B attempts to access User A's meal directly -> 404
    resp = client.delete(f"/api/v1/me/meals/{meal_a['id']}", headers={"X-CSRF-Token": csrf_b})
    assert resp.status_code == 404


# ==============================================================================
# Feature B: Google Search Grounding Tests
# ==============================================================================

def test_search_routing_heuristics():
    # Generic nutrition queries -> should NOT use search
    assert should_use_search("100 gram tavuk göğsü kaç kalori?") is False
    assert should_use_search("Bugün ne yedim?") is False
    assert should_use_search("1 porsiyon mercimek çorbası") is False
    assert should_use_search("Kilo vermek için kaç kalori almalıyım?") is False

    # Branded food queries -> SHOULD use search
    assert should_use_search("Starbucks Caramel Frappuccino venti kaç kalori?") is True
    assert should_use_search("McDonald's Big Mac menü besin değerleri") is True
    assert should_use_search("Getir'den aldığım Eti Karam Gurme kalori") is True
    assert should_use_search("Burger King Whopper kaç gram protein?") is True
    assert should_use_search("Migros filtre kahve") is True

    # Current event / recent update queries -> SHOULD use search
    assert should_use_search("2026 Türkiye beslenme rehberi güncellemeleri nelerdir?") is True
    assert should_use_search("Son araştırmalar aralıklı oruç hakkında ne diyor?") is True
    assert should_use_search("Bu yıl çıkan yeni protein tozu markaları") is True


def test_chat_search_grounding_invoked_for_branded_food(smart_inputs_env):
    from uuid import uuid4
    from app.services.gemini_service import ProviderResult, Usage
    client, _, settings, session_factory, fake_provider = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    # Queue reply with grounding sources
    fake_provider.replies.clear()
    fake_provider.replies.append(
        ProviderResult(
            text="Starbucks White Chocolate Mocha venti boyu yaklaşık 530 kaloridir.",
            usage=Usage(100, 50, 150),
            grounding_sources=[{"title": "Starbucks Menu", "url": "https://www.starbucks.com/menu"}],
        )
    )

    # Create conversation
    conv_resp = client.post("/api/v1/me/conversations", headers={"X-CSRF-Token": csrf})
    assert conv_resp.status_code == 201
    conv = conv_resp.json()
    conv_id = conv["id"]

    # Send branded search query
    msg_resp = client.post(
        f"/api/v1/me/conversations/{conv_id}/messages",
        headers={"X-CSRF-Token": csrf},
        json={
            "content": "Starbucks White Chocolate Mocha venti kaç kalori?",
            "client_request_id": str(uuid4()),
        },
    )
    assert msg_resp.status_code == 201
    data = msg_resp.json()

    # Verify provider was called with enable_search=True
    coach_calls = [call for call in fake_provider.calls if call[0] == "coach"]
    assert len(coach_calls) > 0
    assert coach_calls[-1][1].get("_enable_search") is True

    # Verify assistant message contains grounding sources
    assistant_msg = data["assistant_message"]
    assert "grounding_sources" in assistant_msg
    assert len(assistant_msg["grounding_sources"]) >= 1
    assert assistant_msg["grounding_sources"][0]["url"] == "https://www.starbucks.com/menu"


def test_chat_generic_query_has_empty_grounding_sources(smart_inputs_env):
    from uuid import uuid4
    client, _, settings, session_factory, fake_provider = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    conv_resp = client.post("/api/v1/me/conversations", headers={"X-CSRF-Token": csrf})
    assert conv_resp.status_code == 201
    conv = conv_resp.json()
    conv_id = conv["id"]

    # Send generic nutrition query
    msg_resp = client.post(
        f"/api/v1/me/conversations/{conv_id}/messages",
        headers={"X-CSRF-Token": csrf},
        json={
            "content": "100 gram elma kaç kalori?",
            "client_request_id": str(uuid4()),
        },
    )
    assert msg_resp.status_code == 201
    data = msg_resp.json()

    # Verify provider was called with enable_search=False
    coach_calls = [call for call in fake_provider.calls if call[0] == "coach"]
    assert len(coach_calls) > 0
    assert coach_calls[-1][1].get("_enable_search") is False

    # Verify grounding sources is an empty list (no fake citations)
    assistant_msg = data["assistant_message"]
    assert assistant_msg["grounding_sources"] == []


def test_chat_idempotency_preserved_with_grounding(smart_inputs_env):
    from uuid import uuid4
    client, _, settings, session_factory, fake_provider = smart_inputs_env
    reg = register_user(client)
    assert reg.status_code == 201
    csrf = get_csrf(client, session_factory, settings)

    conv_resp = client.post("/api/v1/me/conversations", headers={"X-CSRF-Token": csrf})
    assert conv_resp.status_code == 201
    conv = conv_resp.json()
    conv_id = conv["id"]

    req_id = str(uuid4())

    # Send first request (creates new message -> 201)
    resp1 = client.post(
        f"/api/v1/me/conversations/{conv_id}/messages",
        headers={"X-CSRF-Token": csrf},
        json={
            "content": "Starbucks Iced Latte kalori?",
            "client_request_id": req_id,
        },
    )
    assert resp1.status_code == 201
    data1 = resp1.json()
    initial_calls = len(fake_provider.calls)

    # Retry same client_request_id (idempotent replay -> 200)
    resp2 = client.post(
        f"/api/v1/me/conversations/{conv_id}/messages",
        headers={"X-CSRF-Token": csrf},
        json={
            "content": "Starbucks Iced Latte kalori?",
            "client_request_id": req_id,
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()

    # Calls should not have increased (idempotent cache hit)
    assert len(fake_provider.calls) == initial_calls
    assert data1["assistant_message"]["id"] == data2["assistant_message"]["id"]
    assert data1["assistant_message"]["grounding_sources"] == data2["assistant_message"]["grounding_sources"]
