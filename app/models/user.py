from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=True)
    profile: Mapped["UserProfile"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    sessions: Mapped[list["AuthSession"]] = relationship(
        "AuthSession", back_populates="user", cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = tuple(
        CheckConstraint(f"{field} IS NULL OR {field} > 0", name=f"ck_profile_{field}")
        for field in ("height_cm", "goal_weight_kg", "calorie_target")
    ) + tuple(
        CheckConstraint(f"{field} IS NULL OR {field} >= 0", name=f"ck_profile_{field}")
        for field in ("protein_target_g", "carb_target_g", "fat_target_g")
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    biological_sex: Mapped[str | None] = mapped_column(String(20))
    height_cm: Mapped[float | None]
    goal_weight_kg: Mapped[float | None]
    activity_level: Mapped[str | None] = mapped_column(String(30))
    calorie_target: Mapped[int | None]
    protein_target_g: Mapped[float | None]
    carb_target_g: Mapped[float | None]
    fat_target_g: Mapped[float | None]
    preferred_weekly_weight_change_kg: Mapped[float | None]
    goal_type: Mapped[str | None] = mapped_column(String(20))
    training_frequency: Mapped[str | None] = mapped_column(String(20))
    pace_percent_per_week: Mapped[float | None] = mapped_column(Float)
    pregnancy_or_breastfeeding: Mapped[bool | None] = mapped_column(Boolean)
    dietary_exclusions: Mapped[list | None] = mapped_column(JSON)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Versioned, deterministic goal snapshot. Current weight always comes from WeightLog.
    bmr_kcal: Mapped[int | None] = mapped_column(Integer)
    estimated_expenditure_kcal: Mapped[int | None] = mapped_column(Integer)
    expenditure_source: Mapped[str | None] = mapped_column(String(30))
    planned_rate_kg_per_week: Mapped[float | None] = mapped_column(Float)
    planned_eta_earliest: Mapped[date | None] = mapped_column(Date)
    planned_eta_latest: Mapped[date | None] = mapped_column(Date)
    eta_source: Mapped[str | None] = mapped_column(String(30))
    plan_status: Mapped[str | None] = mapped_column(String(40))
    plan_constraint_reason: Mapped[str | None] = mapped_column(String(200))
    calculation_version: Mapped[str | None] = mapped_column(String(30))
    targets_recalculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    user: Mapped[User] = relationship(back_populates="profile")
