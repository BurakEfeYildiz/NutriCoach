"""Structured recipes and explicit dietary exclusions for Product V2 Sprint 3."""
from alembic import op
import sqlalchemy as sa

from app.db.types import Amount

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_profiles", sa.Column("dietary_exclusions", sa.JSON(), nullable=True))
    op.create_table("recipes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("source", sa.String(30), nullable=False), sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("description", sa.String(800), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False), sa.Column("instructions", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_key", name="uq_recipe_source_key"),
        sa.CheckConstraint("servings > 0", name="ck_recipe_servings"),
        sa.CheckConstraint("(source = 'curated' AND owner_user_id IS NULL) OR (source != 'curated' AND owner_user_id IS NOT NULL)", name="ck_recipe_owner"))
    op.create_index("ix_recipes_owner", "recipes", ["owner_user_id"])
    op.create_table("recipe_ingredients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipe_id", sa.String(36), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("food_id", sa.String(36), sa.ForeignKey("foods.id", ondelete="SET NULL")),
        sa.Column("portion_id", sa.String(36), sa.ForeignKey("food_portions.id", ondelete="SET NULL")),
        sa.Column("quantity", Amount(), nullable=False), sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("fallback_text", sa.String(200)), sa.Column("allergen_tags", sa.JSON(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_recipe_ingredient_quantity"),
        sa.CheckConstraint("food_id IS NOT NULL OR fallback_text IS NOT NULL", name="ck_recipe_ingredient_source"))
    op.create_index("ix_recipe_ingredients_recipe", "recipe_ingredients", ["recipe_id"])


def downgrade():
    op.drop_index("ix_recipe_ingredients_recipe", table_name="recipe_ingredients")
    op.drop_table("recipe_ingredients")
    op.drop_index("ix_recipes_owner", table_name="recipes")
    op.drop_table("recipes")
    with op.batch_alter_table("user_profiles") as batch:
        batch.drop_column("dietary_exclusions")
