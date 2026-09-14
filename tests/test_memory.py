from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.core.config import Settings
from app.models.chat import Message
from app.models.memory import Memory
from app.schemas.memory import MemoryCandidate, MemoryExtractionResult
from app.services.context_service import build_coach_context
from app.services.memory_service import (
    deactivate_memory,
    is_sensitive_candidate,
    list_active_memories,
    persist_candidate,
    should_extract_memories,
)
from tests.fakes import FakeGeminiProvider, intent, memory_result


def test_pre_filter_heuristics():
    # Negative cases (should NOT trigger extraction)
    assert not should_extract_memories("Merhaba, nasılsın?")
    assert not should_extract_memories("200g tavuk ve 100g pilav yedim")
    assert not should_extract_memories("Kilo: 75.5")
    assert not should_extract_memories("Bugün çok yoruldum")
    assert not should_extract_memories("Günaydın")

    # Positive cases (durable preference indicators)
    assert should_extract_memories("Ben vejetaryenim")
    assert should_extract_memories("Yulaf sevmiyorum")
    assert should_extract_memories("Kahveye bayılırım")
    assert should_extract_memories("Laktoz alerjim var")
    assert should_extract_memories("Genelde sabahları spor yaparım")
    assert should_extract_memories("Tavuk asla yemem")


def test_sensitive_candidate_filtering():
    sensitive_1 = MemoryCandidate(
        category="practical_constraint",
        key="diyabet_ilaci",
        value="Kullanıcı metformin kullanıyor",
        confidence=0.9,
    )
    assert is_sensitive_candidate(sensitive_1)

    sensitive_2 = MemoryCandidate(
        category="practical_constraint",
        key="kanser",
        value="Kullanıcı kemoterapi görüyor",
        confidence=0.95,
    )
    assert is_sensitive_candidate(sensitive_2)

    safe_candidate = MemoryCandidate(
        category="food_dislike",
        key="patlican",
        value="Patlıcan sevmiyor",
        confidence=0.9,
    )
    assert not is_sensitive_candidate(safe_candidate)


def test_memory_persistence_and_confidence_threshold(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        user_id = users[0]
        # Low confidence (< 0.60) ignored
        low_conf = MemoryCandidate(
            category="food_preference",
            key="elma",
            value="Belki elma sever",
            confidence=0.50,
        )
        saved_low = persist_candidate(session, user_id, low_conf)
        assert saved_low is None

        # High confidence persisted
        high_conf = MemoryCandidate(
            category="food_preference",
            key="elma",
            value="Elmayı çok sever",
            confidence=0.90,
        )
        saved_high = persist_candidate(session, user_id, high_conf)
        session.commit()
        assert saved_high is not None
        assert saved_high.status == "active"
        assert saved_high.key == "elma"
        assert float(saved_high.confidence) == 0.90

        active = list_active_memories(session, user_id)
        assert len(active) == 1
        assert active[0].id == saved_high.id


def test_memory_deduplication(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        user_id = users[0]
        c1 = MemoryCandidate(
            category="food_dislike",
            key="kereviz",
            value="Kereviz yemiyor",
            confidence=0.85,
        )
        m1 = persist_candidate(session, user_id, c1)
        session.commit()
        assert m1 is not None

        c2 = MemoryCandidate(
            category="food_dislike",
            key="kereviz",
            value="Kerevizi hiç sevmez",
            confidence=0.95,
        )
        m2 = persist_candidate(session, user_id, c2)
        session.commit()
        assert m2 is not None
        assert m1.id == m2.id
        assert m2.value == "Kerevizi hiç sevmez"
        assert float(m2.confidence) == 0.95

        active = list_active_memories(session, user_id)
        assert len(active) == 1


def test_memory_contradiction_supersession(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        user_id = users[0]
        dislike = MemoryCandidate(
            category="food_dislike",
            key="yogurt",
            value="Yoğurt sevmiyor",
            confidence=0.90,
        )
        m_dislike = persist_candidate(session, user_id, dislike)
        session.commit()
        assert m_dislike.status == "active"

        like = MemoryCandidate(
            category="food_preference",
            key="yogurt",
            value="Artık yoğurt seviyor",
            confidence=0.92,
        )
        m_like = persist_candidate(session, user_id, like)
        session.commit()
        assert m_like.status == "active"
        assert m_like.id != m_dislike.id

        session.refresh(m_dislike)
        assert m_dislike.status == "superseded"

        active = list_active_memories(session, user_id)
        assert len(active) == 1
        assert active[0].id == m_like.id
        assert active[0].category == "food_preference"


def test_user_isolation(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        u1, u2 = users[0], users[1]
        c1 = MemoryCandidate(
            category="food_preference",
            key="kahve",
            value="Filtre kahve sever",
            confidence=0.90,
        )
        persist_candidate(session, u1, c1)

        c2 = MemoryCandidate(
            category="food_dislike",
            key="cay",
            value="Çay sevmez",
            confidence=0.90,
        )
        persist_candidate(session, u2, c2)
        session.commit()

        user1_memories = list_active_memories(session, u1)
        user2_memories = list_active_memories(session, u2)

        assert len(user1_memories) == 1
        assert user1_memories[0].key == "kahve"

        assert len(user2_memories) == 1
        assert user2_memories[0].key == "cay"


def test_chat_pipeline_extracts_and_persists_memory(chat_env):
    client, app, fake, users, conversations = chat_env
    fake.memories.appendleft(
        memory_result(
            candidates=[
                {
                    "category": "food_dislike",
                    "key": "yumurta",
                    "value": "Kahvaltıda yumurta sevmiyor",
                    "confidence": 0.95,
                    "evidence": "yumurta sevmiyorum",
                }
            ]
        )
    )

    url = f"/api/v1/users/{users[0]}/conversations/{conversations[0]}/messages"
    resp = client.post(url, json={"content": "Kahvaltıda yumurta sevmiyorum.", "client_request_id": str(uuid4())})
    assert resp.status_code == 201

    with app.state.session_factory() as session:
        memories = list_active_memories(session, users[0])
        assert len(memories) == 1
        assert memories[0].key == "yumurta"
        assert memories[0].category == "food_dislike"
        assert memories[0].source_message_id is not None


def test_temporary_statement_prefilter_blocks_extraction(chat_env):
    client, app, fake, users, conversations = chat_env
    # "Bugün canım yumurta istemiyor" -> prefilter returns False, no extraction called
    url = f"/api/v1/users/{users[0]}/conversations/{conversations[0]}/messages"
    resp = client.post(url, json={"content": "Bugün canım yumurta istemiyor.", "client_request_id": str(uuid4())})
    assert resp.status_code == 201

    with app.state.session_factory() as session:
        memories = list_active_memories(session, users[0])
        assert len(memories) == 0


def test_memory_extraction_failure_does_not_break_chat(chat_env):
    client, app, fake, users, conversations = chat_env

    def fail_memory(*args, **kwargs):
        raise RuntimeError("Gemini memory extraction temporary failure")

    fake.extract_memories = fail_memory

    url = f"/api/v1/users/{users[0]}/conversations/{conversations[0]}/messages"
    # Even if memory extraction fails, chat response completes normally
    resp = client.post(url, json={"content": "200g tavuk yedim, ayrıca artık yulaf sevmiyorum.", "client_request_id": str(uuid4())})
    assert resp.status_code == 201
    assert resp.json()["assistant_message"]["content"] is not None


def test_explicit_forget_command(chat_env):
    client, app, fake, users, conversations = chat_env
    with app.state.session_factory() as session:
        c = MemoryCandidate(
            category="food_dislike",
            key="yumurta",
            value="Yumurta sevmiyor",
            confidence=0.90,
        )
        persist_candidate(session, users[0], c)
        session.commit()

    url = f"/api/v1/users/{users[0]}/conversations/{conversations[0]}/messages"
    resp = client.post(url, json={"content": "Yumurta sevmediğimi unut", "client_request_id": str(uuid4())})
    assert resp.status_code == 201

    with app.state.session_factory() as session:
        active = list_active_memories(session, users[0])
        assert len(active) == 0


def test_context_engine_relevance_filtering(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        u = users[0]
        c1 = MemoryCandidate(
            category="food_dislike",
            key="patlican",
            value="Patlıcan sevmez",
            confidence=0.90,
        )
        c2 = MemoryCandidate(
            category="exercise_routine",
            key="kosu",
            value="Pazar günleri koşar",
            confidence=0.85,
        )
        persist_candidate(session, u, c1)
        persist_candidate(session, u, c2)
        session.commit()

        # Greeting query -> memories not included
        ctx_greeting = build_coach_context(
            session=session,
            user_id=u,
            current_message="Günaydın, harika bir gün!",
            now=datetime.now(timezone.utc),
        )
        assert len(ctx_greeting.memories) == 0

        # Meal recommendation query -> food_dislike included
        ctx_meal = build_coach_context(
            session=session,
            user_id=u,
            current_message="Akşam ne yemek önerirsin?",
            now=datetime.now(timezone.utc),
        )
        assert len(ctx_meal.memories) == 1
        assert ctx_meal.memories[0].key == "patlican"


def test_context_memory_hard_limit(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        u = users[0]
        for i in range(15):
            c = MemoryCandidate(
                category="food_preference",
                key=f"yiyecek_{i}",
                value=f"Yiyecek {i} sever",
                confidence=0.80 + (i * 0.01),
            )
            persist_candidate(session, u, c)
        session.commit()

        ctx = build_coach_context(
            session=session,
            user_id=u,
            current_message="Bana yemek tarifleri ve beslenme önerisi verir misin?",
            now=datetime.now(timezone.utc),
        )
        assert len(ctx.memories) == 10
        assert ctx.memory_count_available == 15
        assert ctx.memory_detail_truncated is True


def test_api_memories_crud(client: TestClient, nutrition_app, users):
    u1, u2 = users[0], users[1]
    with nutrition_app.state.session_factory() as session:
        c1 = MemoryCandidate(
            category="food_preference",
            key="kahve",
            value="Filtre kahve sever",
            confidence=0.95,
        )
        m = persist_candidate(session, u1, c1)
        session.commit()
        mem_id = m.id

    # GET user memories
    resp = client.get(f"/api/v1/users/{u1}/memories")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["key"] == "kahve"
    assert data[0]["status"] == "active"

    # Other user cannot see user1 memories
    resp_other = client.get(f"/api/v1/users/{u2}/memories")
    assert resp_other.status_code == 200
    assert len(resp_other.json()) == 0

    # Cross-user delete forbidden (404)
    resp_del_wrong = client.delete(f"/api/v1/users/{u2}/memories/{mem_id}")
    assert resp_del_wrong.status_code == 404

    # Deactivate memory
    resp_del = client.delete(f"/api/v1/users/{u1}/memories/{mem_id}")
    assert resp_del.status_code == 204

    # Now GET returns empty
    resp_after = client.get(f"/api/v1/users/{u1}/memories")
    assert resp_after.status_code == 200
    assert len(resp_after.json()) == 0

    # Getting with include_inactive=True shows deleted
    resp_all = client.get(f"/api/v1/users/{u1}/memories?include_inactive=true")
    assert resp_all.status_code == 200
    assert len(resp_all.json()) == 1
    assert resp_all.json()[0]["status"] == "deleted"
