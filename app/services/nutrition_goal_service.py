"""Deterministic adult nutrition planning; the LLM never performs these calculations."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

CALCULATION_VERSION = "msj-v1"
KCAL_PER_KG = Decimal("7700")
ACTIVITY_FACTORS = {
    "sedentary": Decimal("1.20"),
    "light": Decimal("1.375"),
    "moderate": Decimal("1.55"),
    "active": Decimal("1.725"),
    "very_active": Decimal("1.90"),  # Backward-compatible legacy value.
}
PACE_PRESETS = {"gentle": Decimal("0.25"), "recommended": Decimal("0.50"), "faster": Decimal("0.75")}


class GoalCalculationError(ValueError):
    pass


@dataclass(frozen=True)
class GoalInputs:
    birth_date: date
    biological_sex: str
    height_cm: Decimal
    current_weight_kg: Decimal
    target_weight_kg: Decimal
    goal_type: str
    activity_level: str
    training_frequency: str
    pace_percent_per_week: Decimal
    pregnancy_or_breastfeeding: bool = False


@dataclass(frozen=True)
class GoalPlan:
    age: int
    status: str
    constraint_reason: str | None
    bmr_kcal: int | None
    estimated_expenditure_kcal: int | None
    expenditure_source: str | None
    daily_calorie_target: int | None
    protein_target_g: int | None
    carbohydrate_target_g: int | None
    fat_target_g: int | None
    planned_rate_percent_per_week: Decimal
    planned_rate_kg_per_week: Decimal
    planned_eta_earliest: date | None
    planned_eta_latest: date | None
    eta_source: str | None
    calculation_version: str


def decimal(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise GoalCalculationError("Sonlu bir sayı gerekli.")
    return result


def age_on(birth_date: date, on_date: date) -> int:
    return on_date.year - birth_date.year - ((on_date.month, on_date.day) < (birth_date.month, birth_date.day))


def round_whole(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_five(value: Decimal) -> int:
    return int((value / Decimal("5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 5)


def calculate_bmr(weight_kg, height_cm, age: int, biological_sex: str) -> Decimal:
    """Mifflin–St Jeor REE estimate in kcal/day for adults."""
    if biological_sex not in {"female", "male"}:
        raise GoalCalculationError("Enerji tahmini için fizyolojik cinsiyet kadın veya erkek olmalıdır.")
    if not 18 <= age <= 120:
        raise GoalCalculationError("Bu yetişkin enerji denklemi yalnızca 18–120 yaş için kullanılır.")
    sex_constant = Decimal("5") if biological_sex == "male" else Decimal("-161")
    return Decimal("10") * decimal(weight_kg) + Decimal("6.25") * decimal(height_cm) - Decimal("5") * age + sex_constant


def estimate_initial_expenditure(bmr, activity_level: str) -> Decimal:
    try:
        factor = ACTIVITY_FACTORS[activity_level]
    except KeyError as exc:
        raise GoalCalculationError("Geçerli bir günlük hareket düzeyi seçin.") from exc
    return decimal(bmr) * factor


def percent_to_kg_per_week(weight_kg, pace_percent) -> Decimal:
    pace = decimal(pace_percent)
    if pace < 0 or pace > Decimal("0.75"):
        raise GoalCalculationError("Haftalık hız %0–%0,75 aralığında olmalıdır.")
    return (decimal(weight_kg) * pace / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_inputs(inputs: GoalInputs, today: date) -> int:
    age = age_on(inputs.birth_date, today)
    if age < 13 or age > 120:
        raise GoalCalculationError("Yaş 13–120 aralığında olmalıdır.")
    if inputs.biological_sex not in {"female", "male"}:
        raise GoalCalculationError("Enerji tahmini için fizyolojik cinsiyet seçin.")
    if not Decimal("100") <= decimal(inputs.height_cm) <= Decimal("250"):
        raise GoalCalculationError("Boy 100–250 cm aralığında olmalıdır.")
    if not Decimal("25") <= decimal(inputs.current_weight_kg) <= Decimal("400"):
        raise GoalCalculationError("Güncel kilo 25–400 kg aralığında olmalıdır.")
    if not Decimal("25") <= decimal(inputs.target_weight_kg) <= Decimal("400"):
        raise GoalCalculationError("Hedef kilo 25–400 kg aralığında olmalıdır.")
    if inputs.goal_type == "lose" and inputs.target_weight_kg >= inputs.current_weight_kg:
        raise GoalCalculationError("Kilo verme hedefi güncel kilodan düşük olmalıdır.")
    if inputs.goal_type == "gain" and inputs.target_weight_kg <= inputs.current_weight_kg:
        raise GoalCalculationError("Kilo alma hedefi güncel kilodan yüksek olmalıdır.")
    if inputs.goal_type == "maintain" and abs(inputs.target_weight_kg - inputs.current_weight_kg) > Decimal("1.00"):
        raise GoalCalculationError("Koruma hedefi güncel kilonun en fazla 1 kg yakınında olmalıdır.")
    if inputs.goal_type not in {"lose", "maintain", "gain"}:
        raise GoalCalculationError("Geçerli bir hedef seçin.")
    if inputs.training_frequency not in {"none", "one_two", "three_four", "five_plus"}:
        raise GoalCalculationError("Geçerli bir antrenman sıklığı seçin.")
    if inputs.activity_level not in ACTIVITY_FACTORS:
        raise GoalCalculationError("Geçerli bir günlük hareket düzeyi seçin.")
    pace = decimal(inputs.pace_percent_per_week)
    if inputs.goal_type == "maintain" and pace != 0:
        raise GoalCalculationError("Kilo koruma hedefinde değişim hızı sıfır olmalıdır.")
    if inputs.goal_type != "maintain" and not Decimal("0.20") <= pace <= Decimal("0.75"):
        raise GoalCalculationError("Değişim hızı haftada vücut ağırlığının %0,20–%0,75'i olmalıdır.")
    return age


def calculate_plan(inputs: GoalInputs, today: date) -> GoalPlan:
    age = validate_inputs(inputs, today)
    pace = Decimal("0") if inputs.goal_type == "maintain" else decimal(inputs.pace_percent_per_week)
    rate = percent_to_kg_per_week(inputs.current_weight_kg, pace)

    if age < 18:
        return GoalPlan(age, "unsupported_minor", "18 yaş altı için otomatik enerji hedefi oluşturulmaz.", None, None, None, None, None, None, None, pace, rate, None, None, None, CALCULATION_VERSION)
    if inputs.pregnancy_or_breastfeeding:
        return GoalPlan(age, "unsupported_pregnancy_breastfeeding", "Hamilelik veya emzirme döneminde otomatik kilo hedefi oluşturulmaz.", None, None, None, None, None, None, None, pace, rate, None, None, None, CALCULATION_VERSION)

    bmr = calculate_bmr(inputs.current_weight_kg, inputs.height_cm, age, inputs.biological_sex)
    expenditure = estimate_initial_expenditure(bmr, inputs.activity_level)
    adjustment = rate * KCAL_PER_KG / Decimal("7")
    raw_target = expenditure + (adjustment if inputs.goal_type == "gain" else -adjustment if inputs.goal_type == "lose" else 0)

    # Conservative wellness guardrails; constrained status is visible to the UI.
    floor = max(Decimal("1500") if inputs.biological_sex == "male" else Decimal("1200"), bmr * Decimal("0.80"))
    ceiling = expenditure + Decimal("750")
    constrained = min(max(raw_target, floor), ceiling)
    reason = None
    status = "ready"
    if constrained != raw_target:
        status = "constrained"
        reason = "Seçilen hız güvenli enerji sınırına uymadığı için kalori hedefi sınırlandı."
    calories = Decimal(round_five(constrained))

    protein_factor = Decimal("1.6") if inputs.goal_type in {"lose", "gain"} else Decimal("1.4")
    protein = min(inputs.current_weight_kg * protein_factor, calories * Decimal("0.35") / Decimal("4"))
    fat = max(inputs.current_weight_kg * Decimal("0.8"), calories * Decimal("0.20") / Decimal("9"))
    fat = min(fat, calories * Decimal("0.35") / Decimal("9"))
    carbohydrate = max(Decimal("0"), (calories - protein * Decimal("4") - fat * Decimal("9")) / Decimal("4"))

    eta_early = eta_late = None
    eta_source = None
    if rate > 0:
        planned_weeks = abs(inputs.target_weight_kg - inputs.current_weight_kg) / rate
        eta_early = today + timedelta(days=max(1, round_whole(planned_weeks * Decimal("7") * Decimal("0.85"))))
        eta_late = today + timedelta(days=max(1, round_whole(planned_weeks * Decimal("7") * Decimal("1.25"))))
        eta_source = "planned_range"

    return GoalPlan(age, status, reason, round_whole(bmr), round_whole(expenditure), "initial_estimate", int(calories), round_whole(protein), round_whole(carbohydrate), round_whole(fat), pace, rate, eta_early, eta_late, eta_source, CALCULATION_VERSION)
