"""Deterministic context engine. Python/SQL calculates; Gemini interprets."""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import re
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.chat import Message
from app.models.nutrition import NUTRIENTS
from app.models.user import User, utc_now
from app.schemas.context import (
    CoachContext,
    ItemContext,
    MealContext,
    PeriodSummaryContext,
    ProfileContext,
    RecentChatMessageContext,
    TodayContext,
    WeightContext,
    WeightPointContext,
    YesterdayContext,
)
from app.schemas.intents import IntentPlan, MealCreate, MealDelete, MealUpdate, ProfileUpdate, WeightCreate
from app.schemas.nutrition import Totals
from app.services.nutrition import local_date, meal_totals, range_meals, summarize_day
from app.services.users import get_user
from app.services.weights import list_weights

WEIGHT_TERMS = ('kilo', 'tartı', 'tartıldım', 'zayıflama', 'weight', ' kg')
RECENT_TERMS = ('hafta', '7 gün', '14 gün', 'son zaman', 'nasıl gidiyorum', 'genel durum', 'ortalama', 'ilerleme', 'takip', 'gidişat', 'adherence')
YESTERDAY_TERMS = ('dün', 'yesterday')
TODAY_TERMS = ('bugün', 'öğün', 'kahvaltı', 'öğle', 'akşam', 'ara öğün', 'yedim', 'içtim', 'kalori', 'protein', 'karb', 'yağ', 'makro', 'yediklerim')
PROFILE_TERMS = ('hedef', 'profil', 'boyum', 'boyu', 'yaşım', 'yaşı')
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

    if 'today_nutrition' in categories:
        sections.add('profile')
        sections.add('today')
        if any(term in lower for term in YESTERDAY_TERMS):
            sections.add('yesterday')

    if 'recent_nutrition' in categories:
        sections.add('profile')
        sections.add('today')
        sections.add('yesterday')
        sections.add('recent_7_days')
        sections.add('recent_14_days')
        if any(term in lower for term in WEIGHT_TERMS):
            sections.add('weight')

    if 'weight_progress' in categories:
        sections.add('profile')
        sections.add('weight')
        sections.add('recent_7_days')

    # Enforce deterministic order
    canonical_sections = ['profile', 'today', 'yesterday', 'recent_7_days', 'recent_14_days', 'weight', 'recent_messages']
    included = [s for s in canonical_sections if s in sections]
    sorted_categories = sorted(categories)

    return sorted_categories, included


def compute_profile_context(user: User, now: datetime) -> ProfileContext:
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
        goal_weight_kg=profile.goal_weight_kg,
        preferred_weekly_weight_change_kg=profile.preferred_weekly_weight_change_kg,
        activity_level=profile.activity_level,
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
        remaining_by_target=summary.remaining_by_target,
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

    profile_ctx = compute_profile_context(user, now) if 'profile' in included_sections else None
    today_ctx = compute_today_context(session, user, today, settings.context_max_today_meals) if 'today' in included_sections else None
    yesterday_ctx = compute_yesterday_context(session, user, today - timedelta(days=1)) if 'yesterday' in included_sections else None
    recent_7_ctx = compute_period_summary(session, user, today - timedelta(days=6), today) if 'recent_7_days' in included_sections else None
    recent_14_ctx = compute_period_summary(session, user, today - timedelta(days=13), today) if 'recent_14_days' in included_sections else None
    weight_ctx = compute_weight_context(session, user, settings.context_max_weight_logs) if 'weight' in included_sections else None
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
        today=today_ctx,
        yesterday=yesterday_ctx,
        recent_7_days=recent_7_ctx,
        recent_14_days=recent_14_ctx,
        weight=weight_ctx,
        recent_messages=recent_msgs,
    )
