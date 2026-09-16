"""Canonical food data engine and activity foundation."""
from alembic import op
import sqlalchemy as sa

from app.db.types import Amount

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "foods",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("canonical_name", sa.String(240), nullable=False), sa.Column("normalized_name", sa.String(240), nullable=False),
        sa.Column("brand", sa.String(160)), sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_food_id", sa.String(120), nullable=False), sa.Column("source_data_type", sa.String(80)),
        sa.Column("category", sa.String(160)), sa.Column("barcode", sa.String(80)), sa.Column("country", sa.String(80)),
        sa.Column("basis_type", sa.String(20), nullable=False), sa.Column("basis_amount", Amount(), nullable=False),
        sa.Column("basis_unit", sa.String(20), nullable=False),
        *[sa.Column(name, Amount(), nullable=True) for name in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg")],
        sa.Column("reliability", sa.String(30), nullable=False), sa.Column("source_metadata", sa.JSON()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_food_id", name="uq_food_source_identity"),
        sa.CheckConstraint("basis_type IN ('per_100g','per_100ml','per_serving')", name="ck_food_basis_type"),
        sa.CheckConstraint("basis_amount > 0", name="ck_food_basis_amount"),
        sa.CheckConstraint("(source = 'user' AND owner_user_id IS NOT NULL) OR (source != 'user' AND owner_user_id IS NULL)", name="ck_food_private_ownership"),
        *[sa.CheckConstraint(f"{name} IS NULL OR {name} >= 0", name=f"ck_food_{name}") for name in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg")],
    )
    op.create_index("ix_foods_normalized_name", "foods", ["normalized_name"]); op.create_index("ix_foods_barcode", "foods", ["barcode"]); op.create_index("ix_foods_owner", "foods", ["owner_user_id"])
    op.create_table("food_aliases", sa.Column("id", sa.String(36), primary_key=True), sa.Column("food_id", sa.String(36), sa.ForeignKey("foods.id", ondelete="CASCADE"), nullable=False), sa.Column("alias", sa.String(240), nullable=False), sa.Column("normalized_alias", sa.String(240), nullable=False), sa.Column("language", sa.String(12), nullable=False), sa.Column("source", sa.String(30), nullable=False), sa.UniqueConstraint("food_id", "normalized_alias", "language", name="uq_food_alias"))
    op.create_index("ix_food_alias_normalized", "food_aliases", ["normalized_alias"])
    op.create_table("food_portions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("food_id", sa.String(36), sa.ForeignKey("foods.id", ondelete="CASCADE"), nullable=False), sa.Column("label", sa.String(120), nullable=False), sa.Column("amount", Amount(), nullable=False), sa.Column("unit", sa.String(40), nullable=False), sa.Column("gram_equivalent", Amount()), sa.Column("ml_equivalent", Amount()), sa.Column("serving_equivalent", Amount()), sa.Column("source", sa.String(30), nullable=False), sa.UniqueConstraint("food_id", "label", name="uq_food_portion_label"), sa.CheckConstraint("amount > 0", name="ck_food_portion_amount"), sa.CheckConstraint("gram_equivalent IS NOT NULL OR ml_equivalent IS NOT NULL OR serving_equivalent IS NOT NULL", name="ck_food_portion_has_equivalent"), *[sa.CheckConstraint(f"{n} IS NULL OR {n} > 0", name=f"ck_food_portion_{n}") for n in ("gram_equivalent", "ml_equivalent", "serving_equivalent")])
    op.create_table("favorite_foods", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("food_id", sa.String(36), sa.ForeignKey("foods.id", ondelete="CASCADE"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "food_id", name="uq_favorite_user_food"))
    with op.batch_alter_table("meal_items") as batch:
        batch.add_column(sa.Column("food_id", sa.String(36), nullable=True)); batch.add_column(sa.Column("food_portion_id", sa.String(36), nullable=True)); batch.add_column(sa.Column("food_source", sa.String(30), nullable=True)); batch.add_column(sa.Column("source_food_id", sa.String(120), nullable=True)); batch.add_column(sa.Column("portion_label", sa.String(120), nullable=True))
        batch.create_foreign_key("fk_meal_item_food", "foods", ["food_id"], ["id"], ondelete="SET NULL"); batch.create_foreign_key("fk_meal_item_portion", "food_portions", ["food_portion_id"], ["id"], ondelete="SET NULL")
    op.create_table("daily_steps", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("day", sa.Date(), nullable=False), sa.Column("step_count", sa.Integer(), nullable=False), sa.Column("source", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "day", "source", name="uq_steps_user_day_source"), sa.CheckConstraint("step_count >= 0", name="ck_steps_nonnegative"))
    op.create_index("ix_steps_user_day", "daily_steps", ["user_id", "day"])
    op.create_table("workouts", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("activity_type", sa.String(50), nullable=False), sa.Column("duration_minutes", sa.Integer(), nullable=False), sa.Column("intensity", sa.String(20), nullable=False), sa.Column("met_value", Amount()), sa.Column("estimated_calories", Amount()), sa.Column("calorie_estimate_source", sa.String(30)), sa.Column("source", sa.String(30), nullable=False), sa.Column("notes", sa.String(500)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("duration_minutes > 0", name="ck_workout_duration"), sa.CheckConstraint("met_value IS NULL OR met_value > 0", name="ck_workout_met"), sa.CheckConstraint("estimated_calories IS NULL OR estimated_calories >= 0", name="ck_workout_calories"))
    op.create_index("ix_workouts_user_occurred", "workouts", ["user_id", "occurred_at"])


def downgrade():
    op.drop_index("ix_workouts_user_occurred", table_name="workouts"); op.drop_table("workouts")
    op.drop_index("ix_steps_user_day", table_name="daily_steps"); op.drop_table("daily_steps")
    with op.batch_alter_table("meal_items") as batch:
        batch.drop_constraint("fk_meal_item_portion", type_="foreignkey"); batch.drop_constraint("fk_meal_item_food", type_="foreignkey")
        for name in ("portion_label", "source_food_id", "food_source", "food_portion_id", "food_id"): batch.drop_column(name)
    op.drop_table("favorite_foods"); op.drop_table("food_portions"); op.drop_index("ix_food_alias_normalized", table_name="food_aliases"); op.drop_table("food_aliases")
    op.drop_index("ix_foods_owner", table_name="foods"); op.drop_index("ix_foods_barcode", table_name="foods"); op.drop_index("ix_foods_normalized_name", table_name="foods"); op.drop_table("foods")
