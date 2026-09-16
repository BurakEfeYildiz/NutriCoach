"""Deterministic context engine. Python/SQL calculates; Gemini interprets."""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import re
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.chat import Message
from app.models.memory import Memory
from app.models.nutrition import NUTRIENTS
from app.models.user import User, utc_now
from app.schemas.context import (
    AdaptiveContext,
    ActivityContext,
    ActivityWorkoutContext,
    CoachContext,
    ItemContext,
    MealContext,
    MemoryContext,
    PlanContext,
    PeriodSummaryContext,
    ProfileContext,
    RecentChatMessageContext,
    RecipeSuggestionContext,
    TodayContext,
    WeightContext,
    WeightPointContext,
    YesterdayContext,
)
from app.schemas.intents import IntentPlan, MealCreate, MealDelete, MealUpdate, ProfileUpdate, WeightCreate
from app.schemas.nutrition import Totals
from app.services.memory_service import list_active_memories
from app.services.nutrition import local_date, meal_totals, range_meals, summarize_day
from app.services.users import get_user, nutrition_plan
from app.services.weights import list_weights
from app.services.activity import today_summary as activity_today_summary
from app.services.adaptive_analytics import build_dashboard as build_adaptive_dashboard
from app.services import recipes

WEIGHT_TERMS = ('kilo', 'tartı', 'tartıldım', 'zayıflama', 'weight', ' kg')
RECENT_TERMS = ('hafta', '7 gün', '14 gün', 'son zaman', 'nasıl gidiyorum', 'genel durum', 'ortalama', 'ilerleme', 'takip', 'gidişat', 'adherence')
YESTERDAY_TERMS = ('dün', 'yesterday')
TODAY_TERMS = ('bugün', 'öğün', 'kahvaltı', 'öğle', 'akşam', 'ara öğün', 'yedim', 'içtim', 'kalori', 'protein', 'karb', 'yağ', 'makro', 'yediklerim')
PROFILE_TERMS = ('hedef', 'profil', 'boyum', 'boyu', 'yaşım', 'yaşı')
ACTIVITY_TERMS = ('adım', 'yürüyüş', 'koşu', 'egzersiz', 'antrenman', 'spor', 'aktivite', 'workout', 'steps')
RECIPE_TERMS = ('tarif', 'ne yemeliyim', 'ne yiyebilirim', 'yemek öner', 'recipe', 'what should i eat')
WEEKLY_REVIEW_TERMS = ('haftam', 'haftalık değerlendirme', 'haftalık özet', 'weekly review', 'gelecek hafta')
GREETING_WORDS = frozenset({'merhaba', 'selam', 'selamlar', 'günaydın', 'iyi günler', 'iyi akşamlar', 'teşekkürler', 'sağol', 'hey', 'hi', 'hello'})


def tokenize_text(text: str) -> list[str]:
    return re.findall(r'[\wçğıöşü]+', text.lower())


def select_relevance(plan: IntentPlan | None, message_text: str) -> tuple[list[str], list[str]]:
    categories: set[str] = set()
    lower = message_text.lower()
    tokens = tokenize_text(lower)

    # 1. Inspect structured intent actions
    if plan and plan.actions:
        for action in plan.actions:
            if isinstance(action, (MealCreate, MealUpdate, MealDelete)):
                categories.add('today_nutrition')
            elif isinstance(action, WeightCreate):
                categories.add('weight_progress')
            elif isinstance(action, ProfileUpdate):
                categories.add('profile_goals')

    # 2. Inspect message text using terms
    if any(term in lower for term in WEIGHT_TERMS):
        categories.add('weight_progress')
    if any(term in lower for term in RECENT_TERMS):
        categories.add('recent_nutrition')
    if any(term in lower for term in TODAY_TERMS):
        categories.add('today_nutrition')
    if any(term in lower for term in PROFILE_TERMS):
        categories.add('profile_goals')
    if any(term in lower for term in ACTIVITY_TERMS):
        categories.add('activity_today')
    if any(term in lower for term in RECIPE_TERMS):
        categories.add('recipe_question')

    # 3. Default category if none matched
    if not categories:
        if set(tokens) & GREETING_WORDS or len(tokens) <= 2:
            categories.add('normal_conversation')
        else:
            categories.add('today_nutrition')

    # 4. Map categories to included sections
    sections: set[str] = {'recent_messages'}

    if 'normal_conversation' in categories:
        sections.add('profile')

    if 'profile_goals' in categories:
        sections.add('profile')
        sections.add('today')
        sections.add('memories')

    if 'today_nutrition' in categories:
        sections.add('profile')
        sections.add('today')
        sections.add('memories')
        if any(term in lower for term in YESTERDAY_TERMS):
            sections.add('yesterday')

    if 'recent_nutrition' in categories:
        sections.add('profile')
        sections.add('today')
        sections.add('yesterday')
        sections.add('recent_7_days')
        sections.add('recent_14_days')
        sections.add('memories')
        sections.add('adaptive')
        if any(term in lower for term in WEIGHT_TERMS):
            sections.add('weight')

    if 'weight_progress' in categories:
        sections.add('profile')
        sections.add('weight')
        sections.add('recent_7_days')
        sections.add('memories')
        sections.add('adaptive')

    if 'activity_today' in categories:
        sections.add('profile')
        sections.add('activity')
        sections.add('memories')
        sections.add('adaptive')

    if 'recipe_question' in categories:
        sections.update({'profile', 'today', 'memories', 'adaptive', 'recipe_suggestions'})

    if any(term in lower for term in WEEKLY_REVIEW_TERMS):
        sections.add('adaptive')
        sections.add('weekly_review')

    # Enforce deterministic order
    canonical_sections = ['profile', 'today', 'yesterday', 'recent_7_days', 'recent_14_days', 'weight', 'activity', 'adaptive', 'weekly_review', 'recipe_suggestions', 'memories', 'recent_messages']
    included = [s for s in canonical_sections if s in sections]
    sorted_categories = sorted(categories)

    return sorted_categories, included


def compute_profile_context(user: User, now: datetime, current_weight_kg: Decimal | None = None) -> ProfileContext:
    profile = user.profile
    age = None
    if profile.birth_date:
        today_date = local_date(user, now)
        b = profile.birth_date
        age = today_date.year - b.year - ((today_date.month, today_date.day) < (b.month, b.day))
    return ProfileContext(
        birth_date=profile.birth_date,
        age=age,
        biological_sex=profile.biological_sex,
        height_cm=profile.height_cm,
        current_weight_kg=current_weight_kg,
        goal_weight_kg=profile.goal_weight_kg,
        preferred_weekly_weight_change_kg=profile.preferred_weekly_weight_change_kg,
        activity_level=profile.activity_level,
        goal_type=profile.goal_type,
        training_frequency=profile.training_frequency,
        calorie_target=profile.calorie_target,
        protein_target_g=profile.protein_target_g,
        carb_target_g=profile.carb_target_g,
        fat_target_g=profile.fat_target_g,
        timezone=user.timezone,
    )


def compute_today_context(session: Session, user: User, today: date, max_meals: int) -> TodayContext:
    meals = range_meals(session, user, today, today)
    summary = summarize_day(user, today, meals)

    meal_contexts: list[MealContext] = []
    zone = ZoneInfo(user.timezone)
    for meal in meals:
        item_contexts = [
            ItemContext(
                name=it.name,
                quantity=it.quantity,
                unit=it.unit,
                calories=it.calories,
                protein_g=it.protein_g,
                carbs_g=it.carbs_g,
                fat_g=it.fat_g,
                source=it.source,
                assumptions=it.assumptions,
            )
            for it in meal.items
        ]
        meal_contexts.append(MealContext(
            meal_type=meal.meal_type,
            occurred_at=meal.occurred_at.astimezone(zone).isoformat(),
            original_description=meal.original_description,
            nutrition_source=meal.nutrition_source,
            confidence=meal.confidence,
            totals=meal_totals(meal),
            items=item_contexts,
        ))

    truncated = len(meal_contexts) > max_meals
    displayed_meals = meal_contexts[:max_meals] if truncated else meal_contexts

    return TodayContext(
        date=today,
        has_records=summary.has_records,
        meal_count=summary.meal_count,
        totals=summary.totals,
        calories_consumed=summary.totals.calories if summary.totals else None,
        protein_consumed_g=summary.totals.protein_g if summary.totals else None,
        carbohydrate_consumed_g=summary.totals.carbs_g if summary.totals else None,
        fat_consumed_g=summary.totals.fat_g if summary.totals else None,
        remaining_by_target=summary.remaining_by_target,
        remaining_calories=summary.remaining_by_target.get("calories"),
        remaining_protein_g=summary.remaining_by_target.get("protein_g"),
        remaining_carbohydrate_g=summary.remaining_by_target.get("carbs_g"),
        remaining_fat_g=summary.remaining_by_target.get("fat_g"),
        meals=displayed_meals,
        detail_truncated=truncated,
    )


def compute_yesterday_context(session: Session, user: User, yesterday: date) -> YesterdayContext:
    meals = range_meals(session, user, yesterday, yesterday)
    summary = summarize_day(user, yesterday, meals)
    return YesterdayContext(
        date=yesterday,
        has_records=summary.has_records,
        meal_count=summary.meal_count,
        totals=summary.totals,
    )


def compute_period_summary(session: Session, user: User, start_day: date, end_day: date) -> PeriodSummaryContext:
    days_count = (end_day - start_day).days + 1
    meals = range_meals(session, user, start_day, end_day)
    zone = ZoneInfo(user.timezone)

    grouped = {start_day + timedelta(days=i): [] for i in range(days_count)}
    for meal in meals:
        m_day = meal.occurred_at.astimezone(zone).date()
        if m_day in grouped:
            grouped[m_day].append(meal)

    day_summaries = [summarize_day(user, d, m_list) for d, m_list in grouped.items()]
    recorded = [d.totals for d in day_summaries if d.has_records]
    recorded_days = len(recorded)
    missing_days = days_count - recorded_days

    average = None
    min_calories = None
    max_calories = None
    if recorded:
        average = Totals(**{
            k: (sum((getattr(t, k) for t in recorded), Decimal('0.00')) / len(recorded)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            for k in NUTRIENTS
        })
        calories_list = [t.calories for t in recorded]
        min_calories = min(calories_list)
        max_calories = max(calories_list)

    target = user.profile.calorie_target
    days_above = sum(t.calories > target for t in recorded) if target is not None else None
    days_below = sum(t.calories < target for t in recorded) if target is not None else None

    return PeriodSummaryContext(
        start_date=start_day,
        end_date=end_day,
        days_count=days_count,
        recorded_days=recorded_days,
        missing_days=missing_days,
        average_over_recorded_days=average,
        min_calories_over_recorded_days=min_calories,
        max_calories_over_recorded_days=max_calories,
        days_above_current_calorie_target=days_above,
        days_below_current_calorie_target=days_below,
    )


def compute_weight_context(session: Session, user: User, max_logs: int) -> WeightContext:
    rows = list_weights(session, user.id, limit=max_logs + 1)
    truncated = len(rows) > max_logs
    logs = rows[:max_logs]

    if not logs:
        return WeightContext()

    zone = ZoneInfo(user.timezone)
    current_log = logs[0]
    current_weight_kg = current_log.weight_kg
    current_weight_date = current_log.occurred_at.astimezone(zone).date()

    history = [
        WeightPointContext(
            date=l.occurred_at.astimezone(zone).date(),
            occurred_at=l.occurred_at,
            weight_kg=l.weight_kg,
        )
        for l in logs
    ]

    trend = 'insufficient_data'
    delta_kg = None
    rate_kg_per_week = None

    if len(history) >= 2:
        # history is ordered latest to earliest; earliest is history[-1], latest is history[0]
        latest_pt = history[0]
        earliest_pt = history[-1]
        days_span = (latest_pt.date - earliest_pt.date).days

        if days_span > 0:
            delta_kg = (latest_pt.weight_kg - earliest_pt.weight_kg).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            rate_kg_per_week = (delta_kg * Decimal('7') / Decimal(str(days_span))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            if delta_kg > Decimal('0.50') and rate_kg_per_week > Decimal('0.15'):
                trend = 'increasing'
            elif delta_kg < Decimal('-0.50') and rate_kg_per_week < Decimal('-0.15'):
                trend = 'decreasing'
            else:
                trend = 'stable'
        else:
            delta_kg = (latest_pt.weight_kg - earliest_pt.weight_kg).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            trend = 'insufficient_data'

    return WeightContext(
        current_weight_kg=current_weight_kg,
        current_weight_date=current_weight_date,
        measurement_count=len(history),
        trend=trend,
        delta_kg=delta_kg,
        rate_kg_per_week=rate_kg_per_week,
        history=history,
        detail_truncated=truncated,
    )


def compute_recent_messages(
    session: Session,
    user_id: str,
    conversation_id: str | None,
    message_id: str | None,
    now: datetime,
    limit: int,
    max_chars: int,
) -> list[RecentChatMessageContext]:
    if not conversation_id:
        return []

    rows = list(session.scalars(
        select(Message).where(
            Message.user_id == user_id,
            Message.conversation_id == conversation_id,
            Message.id != message_id,
            Message.status == 'completed',
            Message.created_at <= now,
        ).order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
    ))

    remaining = max_chars
    history = []
    for row in rows:
        content = row.content[:remaining]
        if not content:
            break
        history.append(RecentChatMessageContext(role=row.role, content=content))
        remaining -= len(content)

    return list(reversed(history))


def compute_activity_context(session: Session, user: User, now: datetime) -> ActivityContext:
    summary = activity_today_summary(session, user, now)
    return ActivityContext(
        date=summary.date, has_step_records=bool(summary.steps), total_steps=summary.total_steps,
        total_workout_minutes=summary.total_workout_minutes,
        estimated_activity_calories=summary.estimated_activity_calories,
        workouts=[ActivityWorkoutContext(
            activity_type=row.activity_type, duration_minutes=row.duration_minutes, intensity=row.intensity,
            estimated_calories=row.estimated_calories, calorie_estimate_source=row.calorie_estimate_source,
        ) for row in summary.workouts],
    )


def compute_memories_context(
    session: Session,
    user_id: str,
    categories: list[str],
    max_memories: int,
) -> tuple[list[MemoryContext], int, bool]:
    if categories == ['normal_conversation']:
        allowed = ['coaching_preference']
    elif 'weight_progress' in categories and not ('today_nutrition' in categories or 'recent_nutrition' in categories):
        allowed = ['exercise_routine', 'schedule_routine', 'practical_constraint', 'coaching_preference', 'lifestyle']
    elif 'today_nutrition' in categories or 'recent_nutrition' in categories:
        allowed = ['food_preference', 'food_dislike', 'dietary_habit', 'practical_constraint', 'lifestyle']
    else:
        allowed = None

    count_query = select(func.count()).select_from(Memory).where(Memory.user_id == user_id, Memory.status == 'active')
    if allowed:
        count_query = count_query.where(Memory.category.in_(allowed))
    total_count = session.scalar(count_query) or 0

    all_active = list_active_memories(session, user_id, categories=allowed, limit=max_memories)
    truncated = total_count > max_memories
    return (
        [MemoryContext(category=m.category, key=m.key, value=m.value, confidence=m.confidence) for m in all_active],
        total_count,
        truncated,
    )


def build_coach_context(
    session: Session,
    user_id: str,
    conversation_id: str | None = None,
    message_id: str | None = None,
    current_message: str = "",
    now: datetime | None = None,
    plan: IntentPlan | None = None,
    action_results: list[dict] | None = None,
    settings: Settings | None = None,
) -> CoachContext:
    settings = settings or Settings()
    now = now or utc_now()
    user = get_user(session, user_id)
    today = local_date(user, now)

    categories, included_sections = select_relevance(plan, current_message)

    profile_ctx = None
    plan_ctx = None
    if 'profile' in included_sections:
        saved_plan = nutrition_plan(session, user.id)
        profile_ctx = compute_profile_context(user, now, saved_plan["current_weight_kg"])
        plan_ctx = PlanContext(
            status=saved_plan["status"],
            constraint_reason=saved_plan["constraint_reason"],
            current_weight_kg=saved_plan["current_weight_kg"],
            bmr_kcal=saved_plan["bmr_kcal"],
            estimated_expenditure_kcal=saved_plan["estimated_expenditure_kcal"],
            expenditure_source=saved_plan["expenditure_source"],
            calorie_target=saved_plan["daily_calorie_target"],
            protein_target_g=saved_plan["protein_target_g"],
            carbohydrate_target_g=saved_plan["carbohydrate_target_g"],
            fat_target_g=saved_plan["fat_target_g"],
            planned_rate_percent_per_week=saved_plan["planned_rate_percent_per_week"],
            planned_rate_kg_per_week=saved_plan["planned_rate_kg_per_week"],
            planned_eta_earliest=saved_plan["planned_eta_earliest"],
            planned_eta_latest=saved_plan["planned_eta_latest"],
            eta_source=saved_plan["eta_source"],
            calculation_version=saved_plan["calculation_version"],
        )
    today_ctx = compute_today_context(session, user, today, settings.context_max_today_meals) if 'today' in included_sections else None
    yesterday_ctx = compute_yesterday_context(session, user, today - timedelta(days=1)) if 'yesterday' in included_sections else None
    recent_7_ctx = compute_period_summary(session, user, today - timedelta(days=6), today) if 'recent_7_days' in included_sections else None
    recent_14_ctx = compute_period_summary(session, user, today - timedelta(days=13), today) if 'recent_14_days' in included_sections else None
    weight_ctx = compute_weight_context(session, user, settings.context_max_weight_logs) if 'weight' in included_sections else None
    activity_ctx = compute_activity_context(session, user, now) if 'activity' in included_sections else None
    adaptive_ctx = None
    if 'adaptive' in included_sections:
        dashboard = build_adaptive_dashboard(session, user.id, now)
        suggestions = recipes.recommend(session, user.id, limit=3, now=now, dashboard=dashboard) if 'recipe_suggestions' in included_sections else []
        adaptive_ctx = AdaptiveContext(
            today_logging=dashboard.today_quality, weight_trend=dashboard.weight,
            expenditure=dashboard.expenditure, goal_progress=dashboard.goal,
            nutrition_7d=dashboard.nutrition_7d,
            nutrition_14d=dashboard.nutrition_14d if 'recent_nutrition' in categories or 'recipe_question' in categories else None,
            activity=dashboard.activity if 'activity_today' in categories or 'recent_nutrition' in categories or 'weight_progress' in categories else None,
            pattern_signals=dashboard.patterns[:4], daily_insights=dashboard.insights[:3],
            weekly_review=dashboard.weekly_review if 'weekly_review' in included_sections else None,
            recipe_suggestions=[RecipeSuggestionContext(name=row.name,
                calories=row.per_serving.calories if row.per_serving else None,
                protein_g=row.per_serving.protein_g if row.per_serving else None,
                why_it_fits=row.why_it_fits, nutrition_status=row.nutrition_status) for row in suggestions],
        )
    memories_list, mem_count, mem_truncated = compute_memories_context(
        session, user.id, categories, settings.context_max_memories,
    ) if 'memories' in included_sections else ([], 0, False)
    recent_msgs = compute_recent_messages(
        session, user.id, conversation_id, message_id, now,
        settings.chat_recent_messages, settings.chat_history_chars,
    ) if 'recent_messages' in included_sections else []

    return CoachContext(
        generated_at=now,
        timezone=user.timezone,
        local_date=today,
        categories=categories,
        included_sections=included_sections,
        profile=profile_ctx,
        plan=plan_ctx,
        today=today_ctx,
        yesterday=yesterday_ctx,
        recent_7_days=recent_7_ctx,
        recent_14_days=recent_14_ctx,
        weight=weight_ctx,
        activity=activity_ctx,
        adaptive=adaptive_ctx,
        memories=memories_list,
        memory_count_available=mem_count,
        memory_detail_truncated=mem_truncated,
        recent_messages=recent_msgs,
    )
