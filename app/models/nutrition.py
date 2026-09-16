from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import Amount, UTCDateTime
from app.models.user import utc_now

NUTRIENTS = ('calories', 'protein_g', 'carbs_g', 'fat_g')


def new_id() -> str:
    return str(uuid4())


class Meal(Base):
    __tablename__ = 'meals'
    __table_args__ = (
        UniqueConstraint('user_id', 'id', name='uq_meals_user_id_id'),
        Index('ix_meals_user_occurred', 'user_id', 'occurred_at'),
        CheckConstraint('version > 0', name='ck_meals_version'),
        CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='ck_meals_confidence'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    meal_type: Mapped[str] = mapped_column(String(20))
    original_description: Mapped[str] = mapped_column(String(4000))
    normalized_description: Mapped[str | None] = mapped_column(String(4000))
    nutrition_source: Mapped[str] = mapped_column(String(30), default='manual')
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    items: Mapped[list['MealItem']] = relationship(cascade='all, delete-orphan', passive_deletes=True, order_by='MealItem.id')
    __mapper_args__ = {'version_id_col': version}


class MealItem(Base):
    __tablename__ = 'meal_items'
    __table_args__ = (
        ForeignKeyConstraint(['user_id', 'meal_id'], ['meals.user_id', 'meals.id'], ondelete='CASCADE', name='fk_items_owned_meal'),
        Index('ix_items_user_meal', 'user_id', 'meal_id'),
        CheckConstraint('quantity > 0', name='ck_items_quantity'),
        *(CheckConstraint(f'{f} >= 0', name=f'ck_items_{f}') for f in NUTRIENTS),
        *(CheckConstraint(f"typeof({f}) = 'integer'", name=f'ck_items_{f}_integer').ddl_if(dialect='sqlite') for f in (*NUTRIENTS, 'quantity')),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36))
    meal_id: Mapped[str] = mapped_column(String(36))
    food_id: Mapped[str | None] = mapped_column(ForeignKey('foods.id', ondelete='SET NULL'))
    food_portion_id: Mapped[str | None] = mapped_column(ForeignKey('food_portions.id', ondelete='SET NULL'))
    food_source: Mapped[str | None] = mapped_column(String(30))
    source_food_id: Mapped[str | None] = mapped_column(String(120))
    portion_label: Mapped[str | None] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[Decimal] = mapped_column(Amount())
    unit: Mapped[str] = mapped_column(String(30))
    calories: Mapped[Decimal] = mapped_column(Amount())
    protein_g: Mapped[Decimal] = mapped_column(Amount())
    carbs_g: Mapped[Decimal] = mapped_column(Amount())
    fat_g: Mapped[Decimal] = mapped_column(Amount())
    source: Mapped[str] = mapped_column(String(30), default='manual')
    assumptions: Mapped[str | None] = mapped_column(String(2000))


class WeightLog(Base):
    __tablename__ = 'weight_logs'
    __table_args__ = (
        Index('ix_weights_user_occurred', 'user_id', 'occurred_at'),
        CheckConstraint('weight_kg > 0', name='ck_weights_positive'),
        CheckConstraint("typeof(weight_kg) = 'integer'", name='ck_weights_integer').ddl_if(dialect='sqlite'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    weight_kg: Mapped[Decimal] = mapped_column(Amount())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
