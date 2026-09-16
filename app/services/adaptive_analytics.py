"""Bounded, timezone-aware facts for adaptive coaching; no LLM arithmetic."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import DailySteps, Workout
from app.models.nutrition import Meal, WeightLog, NUTRIENTS
from app.models.user import User, utc_now
from app.schemas.analytics import (
    ActivityAnalytics, ActivityWindow, AdaptiveDashboard, DayQuality, ExpenditureEstimate,
    Gamification, GoalProgress, InsightCandidate, NutritionWindow, PatternSignal,
    TargetSuggestion, WeightTrend, WeeklyReview,
)
from app.schemas.nutrition import Totals
from app.services.nutrition import day_bounds, local_date, meal_totals, range_meals
from app.services.users import get_user

ZERO = Decimal("0")
HUNDRED = Decimal("100")
Q = Decimal(".01")
MAIN = frozenset({"breakfast", "lunch", "dinner"})
TYPES = ("breakfast", "lunch", "dinner", "snack", "extra", "other")
CALORIE_RANGE = (Decimal("0.90"), Decimal("1.10"))
MACRO_RANGE = (Decimal("0.80"), Decimal("1.20"))
WEIGHT_EWMA_HALF_LIFE_DAYS = Decimal("7")
ADAPTIVE_ENERGY_KCAL_PER_KG = Decimal("7000")  # conservative approximation, not physiological identity


def q(value) -> Decimal:
    return Decimal(str(value)).quantize(Q, rounding=ROUND_HALF_UP)


def average_totals(values: list[Totals]) -> Totals | None:
    if not values:
        return None
    return Totals(**{key: q(sum((getattr(v, key) for v in values), ZERO) / len(values)) for key in NUTRIENTS})


def _meal_groups(user: User, meals: list[Meal]) -> dict[date, list[Meal]]:
    zone = ZoneInfo(user.timezone)
    grouped: dict[date, list[Meal]] = defaultdict(list)
    for meal in meals:
        grouped[meal.occurred_at.astimezone(zone).date()].append(meal)
    return grouped


def day_quality(day: date, meals: list[Meal]) -> DayQuality:
    if not meals:
        return DayQuality(date=day, status="none", meal_count=0, distinct_main_meals=0, has_extras=False)
    main_types = {meal.meal_type for meal in meals if meal.meal_type in MAIN}
    main_times = [meal.occurred_at for meal in meals if meal.meal_type in MAIN]
    # Observable heuristic, never a claim that every bite was logged.
    span_ok = len(main_times) >= 2 and (max(main_times) - min(main_times)).total_seconds() >= 4 * 3600
    status = "likely_complete" if len(main_types) >= 3 or (len(main_types) >= 2 and span_ok) else "partial"
    per_meal = [meal_totals(meal) for meal in meals]
    totals = Totals(**{key: sum((getattr(total, key) for total in per_meal), ZERO) for key in NUTRIENTS})
    return DayQuality(date=day, status=status, meal_count=len(meals), distinct_main_meals=len(main_types),
                      has_extras=any(meal.meal_type == "extra" for meal in meals), totals=totals)


def nutrition_window(user: User, grouped: dict[date, list[Meal]], end: date, days: int) -> NutritionWindow:
    dates = [end - timedelta(days=days - 1 - offset) for offset in range(days)]
    qualities = [day_quality(d, grouped.get(d, [])) for d in dates]
    usable = [entry for entry in qualities if entry.status == "likely_complete"]
    totals = [entry.totals for entry in usable]
    targets = {"calories": user.profile.calorie_target, "protein_g": user.profile.protein_target_g,
               "carbs_g": user.profile.carb_target_g, "fat_g": user.profile.fat_target_g}
    def hits(key: str, lower: Decimal, upper: Decimal | None = None):
        target = targets[key]
        if target is None or not usable:
            return None
        target = Decimal(str(target))
        if target <= 0:
            return None
        return sum(lower * target <= getattr(total, key) <= upper * target if upper is not None
                   else getattr(total, key) >= lower * target for total in totals)
    averages = {}
    supports = {}
    for meal_type in TYPES:
        per_day = []
        for entry in usable:
            matching = [meal_totals(meal) for meal in grouped.get(entry.date, []) if meal.meal_type == meal_type]
            if matching:
                per_day.append(Totals(**{key: sum((getattr(t, key) for t in matching), ZERO) for key in NUTRIENTS}))
        averages[meal_type] = average_totals(per_day)
        supports[meal_type] = len(per_day)
    extras = []
    for entry in usable:
        extras.append(sum((meal_totals(meal).calories for meal in grouped.get(entry.date, []) if meal.meal_type == "extra"), ZERO))
    return NutritionWindow(window_days=days, start_date=dates[0], end_date=end,
        logged_days=sum(entry.status != "none" for entry in qualities), usable_days=len(usable),
        missing_days=sum(entry.status == "none" for entry in qualities), average_over_usable_days=average_totals(totals),
        calorie_hit_days=hits("calories", *CALORIE_RANGE), protein_hit_days=hits("protein_g", Decimal("0.90")),
        carb_within_days=hits("carbs_g", *MACRO_RANGE), fat_within_days=hits("fat_g", *MACRO_RANGE),
        meal_averages=averages, meal_support_days=supports,
        extras_average_calories=q(sum(extras, ZERO) / len(extras)) if extras else None)


def _weight_observations(rows: list[WeightLog], user: User):
    zone = ZoneInfo(user.timezone)
    by_day = {}
    for row in sorted(rows, key=lambda r: (r.occurred_at, r.created_at, r.id)):
        by_day[row.occurred_at.astimezone(zone).date()] = row
    observations = []
    previous = None
    previous_day = None
    for day, row in sorted(by_day.items()):
        if previous is None:
            trend = row.weight_kg
        else:
            gap = (day - previous_day).days
            alpha = Decimal(str(1 - 0.5 ** (gap / float(WEIGHT_EWMA_HALF_LIFE_DAYS))))
            trend = previous + alpha * (row.weight_kg - previous)
        trend = q(trend)
        observations.append((day, row, trend))
        previous, previous_day = trend, day
    return observations


def _reference(observations, cutoff: date):
    earlier = [(d, t) for d, _, t in observations if d <= cutoff]
    if not earlier or (cutoff - earlier[-1][0]).days > 7:
        return None
    return earlier[-1]


def weight_trend(user: User, rows: list[WeightLog], today: date) -> tuple[WeightTrend, list]:
    if not rows:
        return WeightTrend(), []
    obs = _weight_observations(rows, user)
    latest_day, latest_row, latest_trend = obs[-1]
    ref7 = _reference(obs, today - timedelta(days=7))
    ref14 = _reference(obs, today - timedelta(days=14))
    change = percent = None
    if ref7 and latest_day > ref7[0]:
        elapsed = (latest_day - ref7[0]).days
        change = q((latest_trend - ref7[1]) * Decimal("7") / elapsed)
        percent = q(change / ref7[1] * HUNDRED) if ref7[1] > 0 else None
    span = (obs[-1][0] - obs[0][0]).days
    age = (today - latest_day).days
    confidence = "insufficient"
    if len(obs) >= 3 and span >= 14 and 0 <= age <= 7 and change is not None:
        confidence = "high" if len(obs) >= 8 and span >= 28 else "medium" if len(obs) >= 5 else "low"
    return WeightTrend(current_raw_weight_kg=latest_row.weight_kg, current_trend_weight_kg=latest_trend,
        trend_weight_7d_ago_kg=ref7[1] if ref7 else None, trend_weight_14d_ago_kg=ref14[1] if ref14 else None,
        weekly_change_kg=change, weekly_change_percent=percent, weigh_in_count=len(obs),
        observation_span_days=span, latest_age_days=age, confidence=confidence), obs


def activity_analytics(user: User, steps: list[DailySteps], workouts: list[Workout], today: date) -> ActivityAnalytics:
    zone = ZoneInfo(user.timezone)
    step_by_day: dict[date, int] = defaultdict(int)
    for row in steps: step_by_day[row.day] += row.step_count
    workout_by_day: dict[date, list[Workout]] = defaultdict(list)
    for row in workouts: workout_by_day[row.occurred_at.astimezone(zone).date()].append(row)
    def window(days):
        start = today - timedelta(days=days - 1)
        counted_steps = [value for day, value in step_by_day.items() if start <= day <= today]
        counted_workouts = [row for day, rows in workout_by_day.items() if start <= day <= today for row in rows]
        calories = [row.estimated_calories for row in counted_workouts if row.estimated_calories is not None]
        return ActivityWindow(window_days=days, step_recorded_days=len(counted_steps),
            average_steps_over_recorded_days=q(sum(counted_steps) / len(counted_steps)) if counted_steps else None,
            workout_count=len(counted_workouts), workout_minutes=sum(row.duration_minutes for row in counted_workouts),
            estimated_workout_calories=sum(calories, ZERO) if calories else None)
    seven, fourteen = window(7), window(14)
    today_steps = step_by_day.get(today)
    return ActivityAnalytics(steps_today=today_steps, days_7=seven, days_14=fourteen,
        steps_vs_7d_average=q(Decimal(today_steps) - seven.average_steps_over_recorded_days)
        if today_steps is not None and seven.average_steps_over_recorded_days is not None and seven.step_recorded_days >= 5 else None)


def expenditure(user: User, trend: WeightTrend, observations: list, grouped: dict[date, list[Meal]], today: date) -> ExpenditureEstimate:
    initial = Decimal(str(user.profile.estimated_expenditure_kcal)) if user.profile.estimated_expenditure_kcal is not None else None
    fallback = ExpenditureEstimate(estimated_expenditure_kcal=initial, initial_estimate_kcal=initial,
        source="initial_estimate" if initial is not None else "unavailable", confidence="low" if initial is not None else "insufficient")
    if initial is None or user.profile.plan_status in {"unsupported_minor", "unsupported_pregnancy_breastfeeding"}:
        return fallback
    cutoff = today - timedelta(days=28)
    old = _reference(observations, cutoff)
    if not old or trend.current_trend_weight_kg is None or trend.confidence not in {"medium", "high"}:
        return fallback
    span = (observations[-1][0] - old[0]).days
    relevant_obs = [entry for entry in observations if entry[0] >= old[0]]
    usable = [day_quality(d, grouped.get(d, [])) for d in (old[0] + timedelta(days=i) for i in range(span + 1))]
    usable = [entry for entry in usable if entry.status == "likely_complete"]
    if span < 28 or len(relevant_obs) < 6 or len(usable) < 21 or Decimal(len(usable)) / (span + 1) < Decimal("0.75"):
        return fallback
    change_percent_per_week = abs((trend.current_trend_weight_kg - old[1]) / old[1] * HUNDRED * Decimal("7") / span)
    if change_percent_per_week > Decimal("1.25"):
        return fallback
    intake = sum((entry.totals.calories for entry in usable), ZERO) / len(usable)
    if not Decimal("1000") <= intake <= Decimal("4500"):
        return fallback
    implied = (old[1] - trend.current_trend_weight_kg) * ADAPTIVE_ENERGY_KCAL_PER_KG / span
    raw = intake + implied
    bounded = min(max(raw, Decimal("1200"), initial - Decimal("300")), Decimal("4500"), initial + Decimal("300"))
    # Blend with the initial estimate; adjustment stays within 150 kcal/day.
    adaptive = q(initial * Decimal("0.50") + bounded * Decimal("0.50"))
    confidence = "high" if len(relevant_obs) >= 8 and Decimal(len(usable)) / (span + 1) >= Decimal("0.85") else "medium"
    return ExpenditureEstimate(estimated_expenditure_kcal=adaptive, initial_estimate_kcal=initial,
        source="adaptive_estimate", confidence=confidence, usable_overlap_days=len(usable), observation_days=span)


def goal_progress(user: User, trend: WeightTrend, today: date) -> GoalProgress:
    profile = user.profile
    target = Decimal(str(profile.goal_weight_kg)) if profile.goal_weight_kg is not None else None
    raw = trend.current_raw_weight_kg
    remaining = abs(target - trend.current_trend_weight_kg) if target is not None and trend.current_trend_weight_kg is not None else None
    actual = trend.weekly_change_percent if trend.confidence in {"medium", "high"} else None
    eta_start = eta_end = None
    if (remaining is not None and remaining > 0 and actual is not None and target is not None
        and profile.goal_type in {"lose", "gain"} and profile.plan_status != "goal_reached"):
        desired_sign = -1 if profile.goal_type == "lose" else 1
        if actual * desired_sign >= Decimal("0.10") and abs(actual) <= Decimal("1.00"):
            weekly_kg = abs(trend.weekly_change_kg)
            if weekly_kg > 0:
                days_needed = remaining / weekly_kg * Decimal("7")
                if days_needed <= Decimal("730"):
                    eta_start = today + timedelta(days=max(1, int(days_needed * Decimal("0.85"))))
                    eta_end = today + timedelta(days=max(1, int(days_needed * Decimal("1.30"))))
    return GoalProgress(status=profile.plan_status, current_weight_kg=raw,
        trend_weight_kg=trend.current_trend_weight_kg, target_weight_kg=target, remaining_weight_kg=q(remaining) if remaining is not None else None,
        planned_rate_percent_per_week=q(Decimal(str(profile.pace_percent_per_week))) if profile.pace_percent_per_week is not None else None,
        actual_rate_percent_per_week=actual, planned_eta_earliest=profile.planned_eta_earliest,
        planned_eta_latest=profile.planned_eta_latest, trend_eta_earliest=eta_start, trend_eta_latest=eta_end)


def pattern_signals(user: User, seven: NutritionWindow, fourteen: NutritionWindow, activity: ActivityAnalytics) -> list[PatternSignal]:
    signals = []
    if seven.usable_days >= 5:
        if seven.protein_hit_days is not None and seven.protein_hit_days <= 2:
            signals.append(PatternSignal(key="protein_below_target", status="recurring", supporting_days=seven.usable_days-seven.protein_hit_days, window_days=7, confidence="medium"))
        if seven.calorie_hit_days is not None and seven.calorie_hit_days <= 2:
            signals.append(PatternSignal(key="calorie_outside_range", status="recurring", supporting_days=seven.usable_days-seven.calorie_hit_days, window_days=7, confidence="medium"))
        if seven.extras_average_calories is not None and seven.extras_average_calories >= Decimal("200"):
            signals.append(PatternSignal(key="extras_contribution", status="observed", magnitude=seven.extras_average_calories,
                supporting_days=seven.usable_days, window_days=7, confidence="medium"))
    if fourteen.usable_days >= 8 and fourteen.meal_support_days.get("breakfast", 0) >= 5:
        avg = fourteen.meal_averages.get("breakfast")
        if avg and user.profile.protein_target_g and avg.protein_g < Decimal(str(user.profile.protein_target_g)) * Decimal("0.20"):
            signals.append(PatternSignal(key="breakfast_protein_baseline", status="below_target_share", magnitude=avg.protein_g,
                supporting_days=fourteen.meal_support_days["breakfast"], window_days=14, confidence="medium"))
    if activity.steps_vs_7d_average is not None and activity.steps_vs_7d_average <= Decimal("-2000"):
        signals.append(PatternSignal(key="steps_below_baseline", status="today", magnitude=activity.steps_vs_7d_average,
            supporting_days=activity.days_7.step_recorded_days, window_days=7, confidence="medium"))
    return signals[:6]


def insight_candidates(user: User, today_quality: DayQuality, grouped: dict[date, list[Meal]], fourteen: NutritionWindow,
                       activity: ActivityAnalytics, patterns: list[PatternSignal], now: datetime) -> list[InsightCandidate]:
    candidates = []
    local_hour = now.astimezone(ZoneInfo(user.timezone)).hour
    totals = today_quality.totals
    if totals and user.profile.protein_target_g and local_hour >= 15:
        target = Decimal(str(user.profile.protein_target_g))
        remaining = target - totals.protein_g
        if remaining >= target * Decimal("0.40"):
            candidates.append(InsightCandidate(type="protein_remaining", priority=80, confidence="medium",
                facts={"consumed_g": totals.protein_g, "remaining_g": q(remaining), "target_g": q(target)},
                text=f"Bugün protein hedefinden yaklaşık {q(remaining)} g kaldı; sonraki öğünde protein kaynağı düşünebilirsin."))
    baseline = fourteen.meal_averages.get("breakfast")
    today_breakfast = [meal_totals(meal) for meal in grouped.get(today_quality.date, []) if meal.meal_type == "breakfast"]
    if baseline and fourteen.meal_support_days.get("breakfast", 0) >= 4 and today_breakfast:
        current = sum((meal.protein_g for meal in today_breakfast), ZERO)
        if baseline.protein_g >= 10 and current < baseline.protein_g * Decimal("0.75"):
            candidates.append(InsightCandidate(type="personal_breakfast_protein", priority=90, confidence="medium",
                facts={"today_g": current, "usual_g": baseline.protein_g},
                text=f"Kahvaltı proteinin {q(current)} g; son günlerdeki kahvaltı ortalaman {baseline.protein_g} g."))
    extras_today = sum((meal_totals(meal).calories for meal in grouped.get(today_quality.date, []) if meal.meal_type == "extra"), ZERO)
    if extras_today >= 150 and fourteen.extras_average_calories is not None and fourteen.usable_days >= 5 and extras_today > fourteen.extras_average_calories * Decimal("1.5"):
        candidates.append(InsightCandidate(type="extras_today", priority=60, confidence="medium",
            facts={"today_kcal": extras_today, "usual_kcal": fourteen.extras_average_calories},
            text=f"Bugünkü ekstralar {q(extras_today)} kcal; kayıtlı günlerdeki ortalaman {fourteen.extras_average_calories} kcal."))
    if activity.steps_vs_7d_average is not None and activity.steps_vs_7d_average <= -2000 and local_hour >= 18:
        candidates.append(InsightCandidate(type="steps_baseline", priority=50, confidence="medium",
            facts={"today_steps": activity.steps_today, "usual_steps": activity.days_7.average_steps_over_recorded_days},
            text=f"Bugünkü adımların {activity.steps_today}; kayıtlı günlerin 7 günlük ortalaması {activity.days_7.average_steps_over_recorded_days}."))
    return sorted(candidates, key=lambda item: -item.priority)[:3]


def gamification(qualities: list[DayQuality], seven: NutritionWindow, fourteen: NutritionWindow,
                 trend: WeightTrend, activity: ActivityAnalytics) -> Gamification:
    complete = {entry.date for entry in qualities if entry.status == "likely_complete"}
    today = qualities[-1].date
    anchor = today if today in complete else today - timedelta(days=1)
    streak = 0
    cursor = anchor
    while cursor in complete:
        streak += 1; cursor -= timedelta(days=1)
    longest = running = 0
    for entry in qualities:
        running = running + 1 if entry.date in complete else 0
        longest = max(longest, running)
    achievements = []
    if complete: achievements.append("first_complete_day")
    if streak >= 3: achievements.append("three_day_logging_streak")
    if streak >= 7: achievements.append("seven_day_logging_streak")
    if seven.usable_days >= 5: achievements.append("five_of_seven_usable_days")
    if seven.usable_days >= 5 and seven.protein_hit_days is not None and seven.protein_hit_days >= 5:
        achievements.append("protein_consistency")
    if trend.weigh_in_count >= 4: achievements.append("regular_weigh_ins")
    if activity.days_14.workout_count >= 4: achievements.append("activity_consistency")
    return Gamification(current_logging_streak=streak, longest_logging_streak_14d=longest,
        logging_consistency_14d_percent=q(Decimal(len(complete)) / 14 * HUNDRED),
        likely_complete_days_14d=len(complete), achievements=achievements)


def target_suggestion(user: User, seven: NutritionWindow, fourteen: NutritionWindow, trend: WeightTrend) -> TargetSuggestion:
    if user.profile.plan_status in {"unsupported_minor", "unsupported_pregnancy_breastfeeding", "goal_reached"}:
        return TargetSuggestion(action="insufficient_data", reason="Bu plan durumunda otomatik hedef önerisi oluşturulmaz.")
    planned = user.profile.pace_percent_per_week
    actual = trend.weekly_change_percent
    if planned is None or actual is None or trend.confidence not in {"medium", "high"} or fourteen.usable_days < 10:
        return TargetSuggestion(action="insufficient_data", reason="Kilo trendi ve örtüşen kullanılabilir beslenme günü henüz yeterli değil.")
    if user.profile.goal_type == "maintain":
        return TargetSuggestion(action="keep_current_target", reason="Koruma hedefi için mevcut plan gözlenmeye devam edilir.")
    signed_plan = -Decimal(str(planned)) if user.profile.goal_type == "lose" else Decimal(str(planned))
    difference = actual - signed_plan
    if seven.usable_days >= 5 and abs(difference) >= Decimal("0.30") and fourteen.calorie_hit_days is not None and fourteen.calorie_hit_days >= 7:
        delta = 100 if difference < 0 else -100
        return TargetSuggestion(action="consider_small_increase" if delta > 0 else "consider_small_decrease",
            proposed_delta_kcal=delta, reason="Trend planlanan hızdan anlamlı biçimde ayrılıyor; küçük bir değişiklik ancak kullanıcı onayıyla değerlendirilebilir.")
    return TargetSuggestion(action="keep_current_target", reason="Şimdilik mevcut hedefi koruyup veri toplamaya devam etmek uygun.")


def build_dashboard(session: Session, user_id: str, now: datetime | None = None) -> AdaptiveDashboard:
    now = now or utc_now()
    user = get_user(session, user_id)
    today = local_date(user, now)
    meals = range_meals(session, user, today - timedelta(days=42), today)
    grouped = _meal_groups(user, meals)
    qualities = [day_quality(today - timedelta(days=13-i), grouped.get(today - timedelta(days=13-i), [])) for i in range(14)]
    seven = nutrition_window(user, grouped, today, 7)
    fourteen = nutrition_window(user, grouped, today, 14)
    oldest, _ = day_bounds(today - timedelta(days=90), user.timezone)
    weight_rows = list(session.scalars(select(WeightLog).where(WeightLog.user_id == user_id, WeightLog.occurred_at >= oldest,
        WeightLog.occurred_at <= now).order_by(WeightLog.occurred_at.desc()).limit(100)))
    weight_rows.reverse()
    trend, observations = weight_trend(user, weight_rows, today)
    steps = list(session.scalars(select(DailySteps).where(DailySteps.user_id == user_id,
        DailySteps.day >= today - timedelta(days=13), DailySteps.day <= today)))
    start, end = day_bounds(today - timedelta(days=13), user.timezone)[0], day_bounds(today, user.timezone)[1]
    workouts = list(session.scalars(select(Workout).where(Workout.user_id == user_id,
        Workout.occurred_at >= start, Workout.occurred_at < end)))
    activity = activity_analytics(user, steps, workouts, today)
    expenditure_result = expenditure(user, trend, observations, grouped, today)
    goal = goal_progress(user, trend, today)
    patterns = pattern_signals(user, seven, fourteen, activity)
    insights = insight_candidates(user, qualities[-1], grouped, fourteen, activity, patterns, now)
    game = gamification(qualities, seven, fourteen, trend, activity)
    suggestion = target_suggestion(user, seven, fourteen, trend)
    interpretation_prompt = "Yedi günlük incelememi yorumla: ne oldu, hangi örüntü önemli ve gelecek hafta neye odaklanmalıyım? Yalnızca verilen deterministik verileri kullan."
    review = WeeklyReview(start_date=seven.start_date, end_date=today, nutrition=seven, weight=trend,
        activity=activity.days_7, expenditure=expenditure_result, goal=goal,
        patterns=patterns[:4], target_suggestion=suggestion, interpretation_prompt=interpretation_prompt)
    return AdaptiveDashboard(date=today, timezone=user.timezone, today_quality=qualities[-1],
        nutrition_7d=seven, nutrition_14d=fourteen, weight=trend, activity=activity,
        expenditure=expenditure_result, goal=goal, patterns=patterns, insights=insights,
        gamification=game, weekly_review=review)
