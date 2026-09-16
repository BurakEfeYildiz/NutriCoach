"""Recipes store ingredient quantities; nutrition is calculated from Food at read time."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import Amount, UTCDateTime
from app.models.user import utc_now


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("source", "source_key", name="uq_recipe_source_key"),
        CheckConstraint("servings > 0", name="ck_recipe_servings"),
        CheckConstraint("(source = 'curated' AND owner_user_id IS NULL) OR (source != 'curated' AND owner_user_id IS NOT NULL)", name="ck_recipe_owner"),
        Index("ix_recipes_owner", "owner_user_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(30))
    source_key: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(800))
    servings: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[list] = mapped_column(JSON)
    tags: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_recipe_ingredient_quantity"),
        CheckConstraint("food_id IS NOT NULL OR fallback_text IS NOT NULL", name="ck_recipe_ingredient_source"),
        Index("ix_recipe_ingredients_recipe", "recipe_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recipe_id: Mapped[str] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    food_id: Mapped[str | None] = mapped_column(ForeignKey("foods.id", ondelete="SET NULL"))
    portion_id: Mapped[str | None] = mapped_column(ForeignKey("food_portions.id", ondelete="SET NULL"))
    quantity: Mapped[Decimal] = mapped_column(Amount())
    unit: Mapped[str] = mapped_column(String(40))
    fallback_text: Mapped[str | None] = mapped_column(String(200))
    allergen_tags: Mapped[list] = mapped_column(JSON)
