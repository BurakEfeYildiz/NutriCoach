from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    profile: Mapped["UserProfile"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    user: Mapped[User] = relationship(back_populates="profile")
