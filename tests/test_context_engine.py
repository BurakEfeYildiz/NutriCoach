from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from app.core.config import Settings
from app.models.chat import Message
from app.models.nutrition import Meal, MealItem, WeightLog
from app.models.user import User, UserProfile
from app.schemas.context import CoachContext
from app.schemas.intents import IntentPlan, MealCreate, NutritionQuestion, WeightCreate
from app.schemas.nutrition import ItemWrite, MealWrite, WeightWrite
from app.services.context_service import (
    build_coach_context,
    compute_period_summary,
    compute_profile_context,
    compute_today_context,
    compute_weight_context,
    compute_yesterday_context,
    select_relevance,
)
from app.services.nutrition import create_meal, local_date
from app.services.weights import create_weight
from tests.fakes import intent
from tests.test_nutrition import meal_payload


def test_relevance_selection_deterministic():
    # 1. Normal conversation
    cats, secs = select_relevance(None, 'Merhaba nasılsın?')
    assert cats == ['normal_conversation']
    assert secs == ['profile', 'recent_messages']

    # 2. Today nutrition question
    cats, secs = select_relevance(None, 'Bugün ne kadar protein aldım?')
    assert 'today_nutrition' in cats
    assert 'today' in secs
    assert 'recent_14_days' not in secs
    assert 'weight' not in secs

    # 3. 14-day / recent history question
    cats, secs = select_relevance(None, 'Son iki haftadır nasıl gidiyorum?')
    assert 'recent_nutrition' in cats
    assert 'recent_7_days' in secs
    assert 'recent_14_days' in secs
    assert 'yesterday' in secs
    assert 'today' in secs

    # 4. Weight question
    cats, secs = select_relevance(None, 'Kilom nasıl gidiyor?')
    assert 'weight_progress' in cats
    assert 'weight' in secs

    # 5. Plan action driven: MealCreate
    mock_plan = IntentPlan(actions=[{'type': 'meal_create', 'meal': meal_payload()}], needs_clarification=False)
    cats, secs = select_relevance(mock_plan, 'Yemek yedim.')
    assert 'today_nutrition' in cats
    assert 'today' in secs

    # 6. Plan action driven: WeightCreate
    mock_weight_plan = IntentPlan(actions=[{'type': 'weight_log_create', 'weight': {'weight_kg': '75.50'}}], needs_clarification=False)
    cats, secs = select_relevance(mock_weight_plan, 'Tartıldım 75.5 kg.')
    assert 'weight_progress' in cats
    assert 'weight' in secs


def test_context_for_user_with_no_nutrition_records(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        ctx = build_coach_context(
            session=session,
            user_id=users[0],
            current_message='Bugün ne yedim?',
            now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        )
        assert isinstance(ctx, CoachContext)
        assert ctx.local_date == date(2026, 9, 14)
        assert ctx.today is not None
        assert ctx.today.has_records is False
        assert ctx.today.meal_count == 0
        assert ctx.today.totals is None
        assert ctx.today.meals == []


def test_today_context_with_recorded_meals(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        payload = meal_payload()
        payload['occurred_at'] = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
        create_meal(session, users[0], MealWrite(**payload))

        ctx = build_coach_context(
            session=session,
            user_id=users[0],
            current_message='Bugün durumum nedir?',
            now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        )
        assert ctx.today.has_records is True
        assert ctx.today.meal_count == 1
        assert ctx.today.totals.calories == Decimal('100.10')
        assert ctx.today.totals.protein_g == Decimal('20.20')
        assert len(ctx.today.meals) == 1
        assert ctx.today.meals[0].meal_type == 'lunch'
        assert len(ctx.today.meals[0].items) == 1
        assert ctx.today.meals[0].items[0].name == 'Tavuk'
        assert ctx.today.detail_truncated is False


def test_missing_day_not_zero_calorie_day(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        user = session.get(User, users[0])
        # Add meal only on 2026-09-10 (1 day recorded out of 7)
        payload = meal_payload()
        payload['occurred_at'] = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
        create_meal(session, users[0], MealWrite(**payload))

        # Range 2026-09-08 to 2026-09-14 (7 days)
        summary = compute_period_summary(session, user, date(2026, 9, 8), date(2026, 9, 14))
        assert summary.days_count == 7
        assert summary.recorded_days == 1
        assert summary.missing_days == 6
        # Average across recorded days must be 100.10, NOT 100.10 / 7!
        assert summary.average_over_recorded_days.calories == Decimal('100.10')
        assert summary.min_calories_over_recorded_days == Decimal('100.10')
        assert summary.max_calories_over_recorded_days == Decimal('100.10')


def test_yesterday_summary_compact(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        user = session.get(User, users[0])
        # Add meal on 2026-09-13
        payload = meal_payload()
        payload['occurred_at'] = datetime(2026, 9, 13, 14, 0, tzinfo=timezone.utc)
        create_meal(session, users[0], MealWrite(**payload))

        yesterday_ctx = compute_yesterday_context(session, user, date(2026, 9, 13))
        assert yesterday_ctx.date == date(2026, 9, 13)
        assert yesterday_ctx.has_records is True
        assert yesterday_ctx.meal_count == 1
        assert yesterday_ctx.totals.calories == Decimal('100.10')


def test_period_summary_7_and_14_days_with_targets(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        user = session.get(User, users[0])
        user.profile.calorie_target = 2000
        session.commit()

        # Day 1: 2026-09-01 (100.10 kcal)
        p1 = meal_payload()
        p1['occurred_at'] = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        create_meal(session, users[0], MealWrite(**p1))

        # Day 2: 2026-09-10 (2500 kcal -> above target)
        p2 = meal_payload()
        p2['occurred_at'] = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        p2['items'][0]['calories'] = Decimal('2500.00')
        create_meal(session, users[0], MealWrite(**p2))

        # 14-day period from 2026-09-01 to 2026-09-14
        summary14 = compute_period_summary(session, user, date(2026, 9, 1), date(2026, 9, 14))
        assert summary14.days_count == 14
        assert summary14.recorded_days == 2
        assert summary14.missing_days == 12
        expected_avg = ((Decimal('100.10') + Decimal('2500.00')) / 2).quantize(Decimal('.01'))
        assert summary14.average_over_recorded_days.calories == expected_avg
        assert summary14.days_above_current_calorie_target == 1
        assert summary14.days_below_current_calorie_target == 1

        # 7-day period from 2026-09-08 to 2026-09-14 (only contains Day 2)
        summary7 = compute_period_summary(session, user, date(2026, 9, 8), date(2026, 9, 14))
        assert summary7.days_count == 7
        assert summary7.recorded_days == 1
        assert summary7.missing_days == 6
        assert summary7.average_over_recorded_days.calories == Decimal('2500.00')
        assert summary7.days_above_current_calorie_target == 1
        assert summary7.days_below_current_calorie_target == 0


def test_timezone_boundary_handling(nutrition_app, users):
    # Europe/Istanbul is UTC+3.
    # 2026-09-13 21:30:00 UTC is 2026-09-14 00:30:00 local!
    # 2026-09-13 20:30:00 UTC is 2026-09-13 23:30:00 local!
    with nutrition_app.state.session_factory() as session:
        user = session.get(User, users[0])
        p1 = meal_payload()
        p1['occurred_at'] = datetime(2026, 9, 13, 20, 30, tzinfo=timezone.utc)
        create_meal(session, users[0], MealWrite(**p1))

        p2 = meal_payload()
        p2['occurred_at'] = datetime(2026, 9, 13, 21, 30, tzinfo=timezone.utc)
        create_meal(session, users[0], MealWrite(**p2))

        # Check today (2026-09-14 local)
        today_ctx = compute_today_context(session, user, date(2026, 9, 14), 10)
        assert today_ctx.meal_count == 1
        assert '2026-09-14T00:30:00+03:00' in today_ctx.meals[0].occurred_at

        # Check yesterday (2026-09-13 local)
        yesterday_ctx = compute_yesterday_context(session, user, date(2026, 9, 13))
        assert yesterday_ctx.meal_count == 1


def test_weight_context_calculations(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        user = session.get(User, users[0])

        # 1. No measurements
        w_ctx = compute_weight_context(session, user, 10)
        assert w_ctx.measurement_count == 0
        assert w_ctx.trend == 'insufficient_data'
        assert w_ctx.current_weight_kg is None

        # 2. Single measurement
        create_weight(session, users[0], WeightWrite(weight_kg=Decimal('80.00'), occurred_at=datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)))
        w_ctx = compute_weight_context(session, user, 10)
        assert w_ctx.measurement_count == 1
        assert w_ctx.current_weight_kg == Decimal('80.00')
        assert w_ctx.trend == 'insufficient_data'

        # 3. Same calendar day measurements (should remain insufficient_data)
        create_weight(session, users[0], WeightWrite(weight_kg=Decimal('80.50'), occurred_at=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc)))
        w_ctx = compute_weight_context(session, user, 10)
        assert w_ctx.measurement_count == 2
        assert w_ctx.current_weight_kg == Decimal('80.50')
        assert w_ctx.trend == 'insufficient_data'

        # 4. Increasing trend (80.50 on Sept 1 -> 83.00 on Sept 15: +2.50 kg over 14 days)
        create_weight(session, users[0], WeightWrite(weight_kg=Decimal('83.00'), occurred_at=datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)))
        w_ctx = compute_weight_context(session, user, 10)
        assert w_ctx.measurement_count == 3
        assert w_ctx.current_weight_kg == Decimal('83.00')
        assert w_ctx.trend == 'increasing'
        assert w_ctx.delta_kg == Decimal('3.00')  # 83.00 - 80.00
        assert w_ctx.rate_kg_per_week is not None

        # 5. Decreasing trend for User B
        create_weight(session, users[1], WeightWrite(weight_kg=Decimal('90.00'), occurred_at=datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)))
        create_weight(session, users[1], WeightWrite(weight_kg=Decimal('88.00'), occurred_at=datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)))
        user_b = session.get(User, users[1])
        w_ctx_b = compute_weight_context(session, user_b, 10)
        assert w_ctx_b.trend == 'decreasing'
        assert w_ctx_b.delta_kg == Decimal('-2.00')

        # 6. Stable trend for User B (add 87.90 on Sept 22: change is -0.10 kg over 7 days)
        create_weight(session, users[1], WeightWrite(weight_kg=Decimal('87.90'), occurred_at=datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)))
        w_ctx_b_stable = compute_weight_context(session, user_b, 2)  # only look at last 2 measurements
        assert w_ctx_b_stable.trend == 'stable'


def test_user_isolation(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        # Create meal and weight for user B
        p = meal_payload()
        p['occurred_at'] = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
        create_meal(session, users[1], MealWrite(**p))
        create_weight(session, users[1], WeightWrite(weight_kg=Decimal('95.00'), occurred_at=datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)))

        # Build context for user A
        ctx_a = build_coach_context(
            session=session,
            user_id=users[0],
            current_message='Bugün durumum ve kilom nedir?',
            now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        )
        assert ctx_a.today.has_records is False
        assert ctx_a.today.meal_count == 0
        assert ctx_a.weight.current_weight_kg is None
        assert ctx_a.weight.measurement_count == 0


def test_recent_conversation_isolation_and_limits(chat_env):
    client, app, fake, users, conversations = chat_env
    # Send first message
    client.post(f'/api/v1/users/{users[0]}/conversations/{conversations[0]}/messages', json={
        'client_request_id': '00000000-0000-0000-0000-000000000001',
        'content': 'İlk mesajım.',
    })

    with app.state.session_factory() as session:
        # Message in conversation 0 should not appear in conversation 1
        ctx_other_conv = build_coach_context(
            session=session,
            user_id=users[0],
            conversation_id=conversations[1],
            current_message='İkinci sohbet mesajı',
        )
        assert ctx_other_conv.recent_messages == []

        # In conversation 0, first completed message should appear, current message excluded
        ctx_same_conv = build_coach_context(
            session=session,
            user_id=users[0],
            conversation_id=conversations[0],
            message_id='pending-msg-id',
            current_message='Yeni mesaj',
        )
        assert len(ctx_same_conv.recent_messages) == 2  # user + assistant from first interaction
        assert ctx_same_conv.recent_messages[0].role == 'user'
        assert ctx_same_conv.recent_messages[0].content == 'İlk mesajım.'
        assert all(m.content != 'Yeni mesaj' for m in ctx_same_conv.recent_messages)


def test_context_detail_truncation(nutrition_app, users):
    with nutrition_app.state.session_factory() as session:
        user = session.get(User, users[0])
        # Add 5 meals
        for i in range(5):
            p = meal_payload()
            p['occurred_at'] = datetime(2026, 9, 14, 8 + i, 0, tzinfo=timezone.utc)
            create_meal(session, users[0], MealWrite(**p))

        # Max meals = 2
        today_ctx = compute_today_context(session, user, date(2026, 9, 14), max_meals=2)
        assert today_ctx.detail_truncated is True
        assert len(today_ctx.meals) == 2
        assert today_ctx.meal_count == 5
        # Crucial requirement: totals must still be computed from ALL 5 meals!
        assert today_ctx.totals.calories == Decimal('100.10') * 5

        # Add 5 weight logs and test max_logs = 2
        for i in range(5):
            create_weight(session, users[0], WeightWrite(weight_kg=Decimal('70.00') + i, occurred_at=datetime(2026, 9, 1 + i, 8, 0, tzinfo=timezone.utc)))
        w_ctx = compute_weight_context(session, user, max_logs=2)
        assert w_ctx.detail_truncated is True
        assert len(w_ctx.history) == 2


def test_post_action_state_in_coach_payload(chat_env):
    client, app, fake, users, conversations = chat_env
    # User message with meal extraction
    meal = meal_payload()
    meal['occurred_at'] = None
    fake.intents.appendleft(intent([{'type': 'meal_create', 'meal': meal}, {'type': 'nutrition_question'}]))

    response = client.post(f'/api/v1/users/{users[0]}/conversations/{conversations[0]}/messages', json={
        'client_request_id': '00000000-0000-0000-0000-000000000002',
        'content': '200g tavuk ve 150g pilav yedim. Bugün durumum nasıl?',
    })
    assert response.status_code == 201

    # Coach call is the second provider call
    assert len(fake.calls) == 2
    coach_phase, coach_payload = fake.calls[1]
    assert coach_phase == 'coach'
    assert 'coach_context' in coach_payload
    coach_ctx = coach_payload['coach_context']

    # Coach context sees post-action meal!
    assert coach_ctx['today']['has_records'] is True
    assert coach_ctx['today']['meal_count'] == 1
    assert coach_ctx['today']['totals']['calories'] == '100.10'
    assert len(coach_ctx['today']['meals']) == 1
    assert coach_ctx['today']['meals'][0]['items'][0]['name'] == 'Tavuk'

    # Legacy convenience keys also present
    assert coach_payload['today']['totals']['calories'] == '100.10'
    assert 'last_7_days' in coach_payload
