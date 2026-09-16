"""Canonical food catalog, aliases, portions and per-user favorites."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import Amount, UTCDateTime
from app.models.user import utc_now


def new_id() -> str:
    return str(uuid4())


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        UniqueConstraint("source", "source_food_id", name="uq_food_source_identity"),
        Index("ix_foods_normalized_name", "normalized_name"),
        Index("ix_foods_barcode", "barcode"),
        Index("ix_foods_owner", "owner_user_id"),
        CheckConstraint("basis_type IN ('per_100g','per_100ml','per_serving')", name="ck_food_basis_type"),
        CheckConstraint("basis_amount > 0", name="ck_food_basis_amount"),
        CheckConstraint(
            "(source = 'user' AND owner_user_id IS NOT NULL) OR (source != 'user' AND owner_user_id IS NULL)",
            name="ck_food_private_ownership",
        ),
        *(CheckConstraint(f"{field} IS NULL OR {field} >= 0", name=f"ck_food_{field}") for field in (
            "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg"
        )),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    canonical_name: Mapped[str] = mapped_column(String(240))
    normalized_name: Mapped[str] = mapped_column(String(240))
    brand: Mapped[str | None] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(30))
    source_food_id: Mapped[str] = mapped_column(String(120))
    source_data_type: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(160))
    barcode: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str | None] = mapped_column(String(80))
    basis_type: Mapped[str] = mapped_column(String(20))
    basis_amount: Mapped[Decimal] = mapped_column(Amount(), default=Decimal("100.00"))
    basis_unit: Mapped[str] = mapped_column(String(20))
    calories: Mapped[Decimal | None] = mapped_column(Amount())
    protein_g: Mapped[Decimal | None] = mapped_column(Amount())
    carbs_g: Mapped[Decimal | None] = mapped_column(Amount())
    fat_g: Mapped[Decimal | None] = mapped_column(Amount())
    fiber_g: Mapped[Decimal | None] = mapped_column(Amount())
    sugar_g: Mapped[Decimal | None] = mapped_column(Amount())
    sodium_mg: Mapped[Decimal | None] = mapped_column(Amount())
    reliability: Mapped[str] = mapped_column(String(30), default="source_reported")
    source_metadata: Mapped[dict | None] = mapped_column(JSON)
    last_synced_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    aliases: Mapped[list["FoodAlias"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    portions: Mapped[list["FoodPortion"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class FoodAlias(Base):
    __tablename__ = "food_aliases"
    __table_args__ = (
        UniqueConstraint("food_id", "normalized_alias", "language", name="uq_food_alias"),
        Index("ix_food_alias_normalized", "normalized_alias"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    food_id: Mapped[str] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(240))
    normalized_alias: Mapped[str] = mapped_column(String(240))
    language: Mapped[str] = mapped_column(String(12), default="tr")
    source: Mapped[str] = mapped_column(String(30), default="curated")


class FoodPortion(Base):
    __tablename__ = "food_portions"
    __table_args__ = (
        UniqueConstraint("food_id", "label", name="uq_food_portion_label"),
        CheckConstraint("amount > 0", name="ck_food_portion_amount"),
        CheckConstraint(
            "gram_equivalent IS NOT NULL OR ml_equivalent IS NOT NULL OR serving_equivalent IS NOT NULL",
            name="ck_food_portion_has_equivalent",
        ),
        *(CheckConstraint(f"{field} IS NULL OR {field} > 0", name=f"ck_food_portion_{field}") for field in (
            "gram_equivalent", "ml_equivalent", "serving_equivalent"
        )),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    food_id: Mapped[str] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Amount(), default=Decimal("1.00"))
    unit: Mapped[str] = mapped_column(String(40))
    gram_equivalent: Mapped[Decimal | None] = mapped_column(Amount())
    ml_equivalent: Mapped[Decimal | None] = mapped_column(Amount())
    serving_equivalent: Mapped[Decimal | None] = mapped_column(Amount())
    source: Mapped[str] = mapped_column(String(30))


class FavoriteFood(Base):
    __tablename__ = "favorite_foods"
    __table_args__ = (UniqueConstraint("user_id", "food_id", name="uq_favorite_user_food"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    food_id: Mapped[str] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
