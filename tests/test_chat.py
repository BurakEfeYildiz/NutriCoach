from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import json
from threading import Event
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.migrate import upgrade_database
from app.main import create_app
from app.models.chat import AIRequest, Conversation, Message
from app.models.nutrition import Meal
from app.schemas.nutrition import MealWrite
from app.services.gemini_service import ProviderError, ProviderResult, Usage
from tests.fakes import FakeGeminiProvider, intent
from tests.test_nutrition import meal_payload



def assert_no_connections(app):
    assert app.state.session_factory.kw['bind'].pool.checkedout() == 0


def messages_path(users, conversations, index=0):
    return f'/api/v1/users/{users[index]}/conversations/{conversations[index]}/messages'


def send(env, content='Merhaba', request_id=None):
    client, _, _, users, conversations = env
    return client.post(messages_path(users, conversations), json={'content': content, 'client_request_id': request_id or str(uuid4())})


def count_meals(app, user):
    with app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(Meal).where(Meal.user_id == user))


def test_normal_chat_persistence_and_usage(chat_env):
    client, app, fake, users, conversations = chat_env
    response = send(chat_env)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body['user_message']['status'] == 'completed'
    assert body['assistant_message']['content'] == 'Merhaba, yardımcı olabilirim.'
    assert body['user_message']['effects_committed'] is False
    history = client.get(messages_path(users, conversations)).json()
    assert [row['role'] for row in history] == ['user', 'assistant']
    assert fake.calls[0][1]['recent_messages'] == []
    with app.state.session_factory() as session:
        logs = list(session.scalars(select(AIRequest).where(AIRequest.user_id == users[0]).order_by(AIRequest.created_at)))
        assert len(logs) == 2
        assert [(r.input_tokens, r.output_tokens, r.total_tokens) for r in logs] == [(120, 45, 190), (210, 30, 270)]
        assert all(r.status == 'completed' and r.latency_ms >= 0 for r in logs)
        assert logs[0].phase == 'intent' and logs[1].phase == 'coach'
    # Re-open with a new app/provider to check persistence across process-style restart.
    with TestClient(create_app(app.state.chat_service.settings, provider=FakeGeminiProvider())) as restarted:
        assert restarted.get(messages_path(users, conversations)).json() == history


@pytest.mark.parametrize('with_question', [False, True])
def test_meal_extraction_and_post_commit_state(chat_env, with_question):
    client, app, fake, users, _ = chat_env
    meal = meal_payload(); meal['occurred_at'] = None
    actions = [{'type': 'meal_create', 'meal': meal}]
    if with_question:
        actions.append({'type': 'nutrition_question'})
    fake.intents.appendleft(intent(actions))
    result = send(chat_env, '200g tavuk ve 150g pilav yedim. Akşam pizza yiyebilir miyim?').json()
    assert result['user_message']['status'] == 'completed'
    assert result['user_message']['effects_committed'] is True
    assert count_meals(app, users[0]) == 1
    assert fake.calls[1][1]['today']['totals']['calories'] == '100.10'
    assert ('last_7_days' in fake.calls[1][1]) is with_question
    record_id = result['user_message']['action_results'][0]['record_id']
    saved = client.get(f'/api/v1/users/{users[0]}/meals/{record_id}').json()
    assert saved['nutrition_source'] == 'estimate'
    assert saved['items'][0]['source'] == 'estimate'
    assert saved['original_description'].startswith('200g tavuk')


@pytest.mark.parametrize('output', [
    '{invalid',
    json.dumps({'actions': [{'type': 'run_sql', 'sql': 'DELETE FROM meals'}], 'needs_clarification': False}),
    intent([{'type': 'meal_create', 'meal': {**meal_payload(), 'items': [{**meal_payload()['items'][0], 'calories': '-1'}]}}]).text,
    intent([{'type': 'meal_create', 'meal': {**meal_payload(), 'items': [{**meal_payload()['items'][0], 'calories': '0.001'}]}}]).text,
    intent([{'type': 'meal_delete', 'target': {'item_name': 'Tavuk', 'meal_id': str(uuid4())}}]).text,
    intent([{'type': 'normal_chat'}], needs_clarification=True, clarification_question='Hangisi?').text,
])
def test_invalid_json_or_schema_no_actions(chat_env, output):
    _, app, fake, users, _ = chat_env
    fake.intents.appendleft(ProviderResult(output, Usage(12, 5, 20)))
    result = send(chat_env).json()
    assert result['user_message']['status'] == 'failed'
    assert result['user_message']['error_type'] == 'invalid_output'
    assert count_meals(app, users[0]) == 0
    assert len(fake.calls) == 1
    with app.state.session_factory() as session:
        log = session.scalar(select(AIRequest).where(AIRequest.user_id == users[0]))
        assert log.status == 'failed' and log.input_tokens == 12


@pytest.mark.parametrize('kind', ['timeout', 'rate_limit', 'authentication', 'network', 'model_unavailable', 'configuration'])
def test_provider_failure_states(chat_env, kind):
    _, app, fake, users, _ = chat_env
    fake.intents.appendleft(ProviderError(kind))
    result = send(chat_env).json()
    assert result['user_message']['error_type'] == kind
    assert result['user_message']['status'] == 'failed'
    assert result['user_message']['effects_committed'] is False
    with app.state.session_factory() as session:
        log = session.scalar(select(AIRequest).where(AIRequest.user_id == users[0]))
        assert log.status == 'failed' and log.input_tokens is None


def test_completed_failed_and_conflicting_retries(chat_env):
    client, app, fake, users, conversations = chat_env
    fake.intents.appendleft(intent([{'type': 'meal_create', 'meal': {**meal_payload(), 'occurred_at': None}}]))
    request_id = str(uuid4())
    first = send(chat_env, 'Tavuk yedim', request_id)
    second = send(chat_env, 'Tavuk yedim', request_id)
    assert second.status_code == 200 and second.json() == first.json()
    assert count_meals(app, users[0]) == 1 and len(fake.calls) == 2
    assert send(chat_env, 'Başka içerik', request_id).status_code == 409
    conversation = client.post(f'/api/v1/users/{users[0]}/conversations').json()['id']
    response = client.post(f'/api/v1/users/{users[0]}/conversations/{conversation}/messages', json={'content': 'Tavuk yedim', 'client_request_id': request_id})
    assert response.status_code == 409
    fake.intents.appendleft(ProviderError('timeout'))
    failed_id = str(uuid4())
    failed = send(chat_env, 'Merhaba', failed_id)
    assert send(chat_env, 'Merhaba', failed_id).json() == failed.json()
    assert len(fake.calls) == 3


def test_inflight_retry_does_not_start_second_pipeline(chat_env):
    client, app, fake, users, conversations = chat_env
    entered, release = Event(), Event()
    def block(phase, _):
        assert_no_connections(app)
        if phase == 'intent':
            entered.set()
            assert release.wait(5)
    fake.on_call = block
    request_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(send, chat_env, 'Merhaba', request_id)
        try:
            assert entered.wait(5)
            retry = send(chat_env, 'Merhaba', request_id)
            assert retry.status_code == 202
            assert retry.json()['user_message']['status'] == 'pending'
            assert retry.json()['assistant_message'] is None
        finally:
            release.set()
        assert first.result(timeout=5).json()['user_message']['status'] == 'completed'
    assert len(fake.calls) == 2


def test_user_and_conversation_scope_and_pagination(chat_env):
    client, app, fake, users, conversations = chat_env
    foreign = f'/api/v1/users/{users[0]}/conversations/{conversations[1]}'
    for path in (foreign, foreign + '/messages'):
        assert client.get(path).status_code == 404
    assert client.post(foreign + '/messages', json={'content': 'Merhaba', 'client_request_id': str(uuid4())}).status_code == 404
    assert fake.calls == []
    send(chat_env)
    assert client.get(messages_path(users, conversations, 1)).json() == []
    page1 = client.get(messages_path(users, conversations) + '?limit=1').json()
    page2 = client.get(messages_path(users, conversations) + '?limit=1&offset=1').json()
    assert page1[0]['id'] != page2[0]['id']
    assert len(client.get(f'/api/v1/users/{users[0]}/conversations?limit=1').json()) == 1
    assert client.get(f'/api/v1/users/{users[0]}/conversations?limit=1&offset=1').json() == []
    fake.intents.appendleft(intent()); fake.replies.append(ProviderResult('Devam'))
    send(chat_env, 'Devam edelim')
    assert len(fake.calls[-2][1]['recent_messages']) == 2
    assert all(row['content'] != 'Devam edelim' for row in fake.calls[-2][1]['recent_messages'])


def test_correction_scales_existing_item_and_delete_preserves_other_items(chat_env):
    client, app, fake, users, _ = chat_env
    payload = meal_payload(); payload['items'].append({**payload['items'][0], 'name': 'Pilav', 'quantity': '150', 'calories': '195'})
    meal = client.post(f'/api/v1/users/{users[0]}/meals', json=payload).json()
    target = {'item_name': 'pilav', 'day': '2026-09-14'}
    fake.intents.appendleft(intent([{'type': 'meal_update', 'target': target, 'quantity': '100', 'unit': 'g'}]))
    result = send(chat_env, 'Pilav 150 değil 100 gramdı.').json()
    assert result['user_message']['status'] == 'completed'
    saved = client.get(f"/api/v1/users/{users[0]}/meals/{meal['id']}").json()
    rice = next(item for item in saved['items'] if item['name'] == 'Pilav')
    assert rice['quantity'] == '100.00' and rice['calories'] == '130.00'
    assert saved['totals']['calories'] == '230.10'
    assert count_meals(app, users[0]) == 1
    fake.intents.appendleft(intent([{'type': 'meal_delete', 'target': target, 'scope': 'item'}]))
    fake.replies.append(ProviderResult('Pilav silindi.'))
    assert send(chat_env, 'Pilavı sil.').json()['user_message']['status'] == 'completed'
    assert len(client.get(f"/api/v1/users/{users[0]}/meals/{meal['id']}").json()['items']) == 1


def test_ambiguous_correction_and_atomic_batch(chat_env):
    client, app, fake, users, _ = chat_env
    for _ in range(2):
        client.post(f'/api/v1/users/{users[0]}/meals', json=meal_payload())
    fake.intents.appendleft(intent([
        {'type': 'meal_create', 'meal': meal_payload()},
        {'type': 'meal_update', 'target': {'item_name': 'Tavuk', 'day': '2026-09-14'}, 'quantity': '250', 'unit': 'g'},
    ]))
    result = send(chat_env, 'Tavuğu 250 gram yap.').json()
    assert 'Birden fazla' in result['assistant_message']['content']
    assert result['user_message']['effects_committed'] is False
    assert count_meals(app, users[0]) == 2 and len(fake.calls) == 1


def test_model_clarification_creates_no_meal(chat_env):
    _, app, fake, users, _ = chat_env
    fake.intents.appendleft(intent([], needs_clarification=True, clarification_question='Yaklaşık kaç kaşık pilav?'))
    result = send(chat_env, 'Biraz pilav yedim').json()
    assert result['assistant_message']['content'] == 'Yaklaşık kaç kaşık pilav?'
    assert count_meals(app, users[0]) == 0 and len(fake.calls) == 1


def test_coach_failure_keeps_committed_meal_and_receipt(chat_env):
    _, app, fake, users, _ = chat_env
    fake.intents.appendleft(intent([{'type': 'meal_create', 'meal': meal_payload()}]))
    fake.replies.appendleft(ProviderError('timeout'))
    request_id = str(uuid4())
    response = send(chat_env, 'Tavuk yedim', request_id)
    result = response.json()
    assert result['user_message']['status'] == 'failed'
    assert result['user_message']['effects_committed'] is True
    assert result['user_message']['action_results'][0]['record_id']
    assert 'kaydedildi' in result['assistant_message']['content']
    assert count_meals(app, users[0]) == 1
    assert send(chat_env, 'Tavuk yedim', request_id).json() == result
    assert len(fake.calls) == 2


def test_weight_profile_actions_and_patch_preserves_fields(chat_env):
    client, app, fake, users, _ = chat_env
    client.put(f'/api/v1/users/{users[0]}/profile', json={'height_cm': 180, 'protein_target_g': 150})
    fake.intents.appendleft(intent([
        {'type': 'weight_log_create', 'weight': {'weight_kg': '97.80', 'occurred_at': None}},
        {'type': 'profile_update', 'changes': {'calorie_target': 2200}},
    ]))
    result = send(chat_env, 'Kilom 97.8, kalori hedefimi 2200 yap').json()
    assert result['user_message']['status'] == 'completed'
    profile = client.get(f'/api/v1/users/{users[0]}/profile').json()
    assert profile['height_cm'] == 180 and profile['protein_target_g'] == 150
    assert profile['calorie_target'] == 2200
    assert client.get(f'/api/v1/users/{users[0]}/weight-logs/current').json()['weight_kg'] == '97.80'


def test_late_action_failure_rolls_back_previous_flush(chat_env, monkeypatch):
    _, app, fake, users, _ = chat_env
    fake.intents.appendleft(intent([
        {'type': 'meal_create', 'meal': meal_payload()},
        {'type': 'weight_log_create', 'weight': {'weight_kg': '90'}},
    ]))
    def fail(*args, **kwargs):
        raise HTTPException(409, 'simulated conflict')
    monkeypatch.setattr('app.services.chat_actions.weights.create_weight', fail)
    result = send(chat_env).json()
    assert result['user_message']['error_type'] == 'action_error'
    assert result['user_message']['effects_committed'] is False
    assert count_meals(app, users[0]) == 0


def test_secret_redaction_in_response_messages_and_log(chat_env, caplog):
    client, app, fake, users, conversations = chat_env
    fake.replies.appendleft(ProviderResult('TEST_SECRET_NOT_FOR_LOGS'))
    response = send(chat_env, 'Merhaba TEST_SECRET_NOT_FOR_LOGS')
    assert 'TEST_SECRET_NOT_FOR_LOGS' not in response.text
    assert 'TEST_SECRET_NOT_FOR_LOGS' not in json.dumps(fake.calls)
    assert 'TEST_SECRET_NOT_FOR_LOGS' not in client.get(messages_path(users, conversations)).text
    with app.state.session_factory() as session:
        logs = list(session.scalars(select(AIRequest).where(AIRequest.user_id == users[0])))
        serialized = json.dumps([{col.name: str(getattr(log, col.name)) for col in AIRequest.__table__.columns} for log in logs])
        assert 'TEST_SECRET_NOT_FOR_LOGS' not in serialized
        assert 'content' not in AIRequest.__table__.columns
        assert 'prompt' not in AIRequest.__table__.columns
    assert 'TEST_SECRET_NOT_FOR_LOGS' not in caplog.text


def test_db_scope_constraints(chat_env):
    _, app, _, users, conversations = chat_env
    result = send(chat_env).json()
    message_id = result['user_message']['id']
    with app.state.session_factory() as session:
        session.add(Message(user_id=users[0], conversation_id=conversations[1], role='user', content='x', client_request_id=str(uuid4())))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(AIRequest(user_id=users[1], message_id=message_id, model='fake', phase='intent'))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(Message(user_id=users[1], conversation_id=conversations[1], role='assistant', content='x', in_reply_to=message_id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_foreign_meal_is_not_a_correction_candidate(chat_env):
    client, app, fake, users, _ = chat_env
    client.post(f'/api/v1/users/{users[1]}/meals', json=meal_payload())
    fake.intents.appendleft(intent([{'type': 'meal_update', 'target': {'item_name': 'Tavuk', 'day': '2026-09-14'}, 'quantity': '250', 'unit': 'gram'}]))
    result = send(chat_env, 'Tavuğu 250 gram yap.').json()
    assert 'bulamadım' in result['assistant_message']['content']
    assert result['user_message']['effects_committed'] is False
    assert count_meals(app, users[0]) == 0 and count_meals(app, users[1]) == 1


def test_history_limit_budget_and_conversation_filter(chat_env):
    client, app, fake, users, conversations = chat_env
    send(chat_env)
    app.state.chat_service.settings.chat_recent_messages = 1
    app.state.chat_service.settings.chat_history_chars = 5
    fake.intents.appendleft(intent()); fake.replies.append(ProviderResult('Kısa yanıt'))
    send(chat_env, 'Devam')
    history = fake.calls[-2][1]['recent_messages']
    assert len(history) == 1 and sum(len(row['content']) for row in history) <= 5
    new_conversation = client.post(f'/api/v1/users/{users[0]}/conversations').json()['id']
    fake.intents.appendleft(intent()); fake.replies.append(ProviderResult('Yeni sohbet'))
    client.post(f'/api/v1/users/{users[0]}/conversations/{new_conversation}/messages', json={'content': 'Yeni', 'client_request_id': str(uuid4())})
    assert fake.calls[-2][1]['recent_messages'] == []


def test_empty_coach_output_keeps_meal(chat_env):
    _, app, fake, users, _ = chat_env
    fake.intents.appendleft(intent([{'type': 'meal_create', 'meal': meal_payload()}]))
    fake.replies.appendleft(ProviderResult('', Usage(20, 0, 20)))
    result = send(chat_env).json()
    assert result['user_message']['effects_committed'] is True
    assert result['user_message']['error_type'] == 'invalid_output'
    assert count_meals(app, users[0]) == 1


def test_delete_last_item_removes_meal(chat_env):
    client, app, fake, users, _ = chat_env
    client.post(f'/api/v1/users/{users[0]}/meals', json=meal_payload())
    fake.intents.appendleft(intent([{'type': 'meal_delete', 'target': {'item_name': 'Tavuk', 'day': '2026-09-14'}}]))
    result = send(chat_env, 'Tavuğu sil').json()
    assert result['user_message']['effects_committed'] is True
    assert count_meals(app, users[0]) == 0


def test_unit_alias_correction(chat_env):
    client, app, fake, users, _ = chat_env
    meal = client.post(f'/api/v1/users/{users[0]}/meals', json=meal_payload()).json()
    fake.intents.appendleft(intent([{'type': 'meal_update', 'target': {'item_name': 'Tavuk', 'day': '2026-09-14'}, 'quantity': '250', 'unit': 'gram'}]))
    result = send(chat_env, 'Tavuğu 250 gram yap').json()
    assert result['user_message']['status'] == 'completed'
    saved = client.get(f"/api/v1/users/{users[0]}/meals/{meal['id']}").json()
    assert saved['items'][0]['quantity'] == '250.00'
    assert saved['items'][0]['calories'] == '125.13'
