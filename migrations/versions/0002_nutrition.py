"""nutrition"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('meals',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('meal_type', sa.String(length=20), nullable=False),
    sa.Column('original_description', sa.String(length=4000), nullable=False),
    sa.Column('normalized_description', sa.String(length=4000), nullable=True),
    sa.Column('nutrition_source', sa.String(length=30), nullable=False),
    sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='ck_meals_confidence'),
    sa.CheckConstraint('version > 0', name='ck_meals_version'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'id', name='uq_meals_user_id_id')
    )
    op.create_index('ix_meals_user_occurred', 'meals', ['user_id', 'occurred_at'], unique=False)
    op.create_table('weight_logs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('weight_kg', sa.Numeric(12, 2).with_variant(sa.BigInteger(), 'sqlite'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("typeof(weight_kg) = 'integer'", name='ck_weights_integer').ddl_if(dialect='sqlite'),
    sa.CheckConstraint('weight_kg > 0', name='ck_weights_positive'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_weights_user_occurred', 'weight_logs', ['user_id', 'occurred_at'], unique=False)
    op.create_table('meal_items',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('meal_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('quantity', sa.Numeric(12, 2).with_variant(sa.BigInteger(), 'sqlite'), nullable=False),
    sa.Column('unit', sa.String(length=30), nullable=False),
    sa.Column('calories', sa.Numeric(12, 2).with_variant(sa.BigInteger(), 'sqlite'), nullable=False),
    sa.Column('protein_g', sa.Numeric(12, 2).with_variant(sa.BigInteger(), 'sqlite'), nullable=False),
    sa.Column('carbs_g', sa.Numeric(12, 2).with_variant(sa.BigInteger(), 'sqlite'), nullable=False),
    sa.Column('fat_g', sa.Numeric(12, 2).with_variant(sa.BigInteger(), 'sqlite'), nullable=False),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('assumptions', sa.String(length=2000), nullable=True),
    sa.CheckConstraint("typeof(calories) = 'integer'", name='ck_items_calories_integer').ddl_if(dialect='sqlite'),
    sa.CheckConstraint("typeof(carbs_g) = 'integer'", name='ck_items_carbs_g_integer').ddl_if(dialect='sqlite'),
    sa.CheckConstraint("typeof(fat_g) = 'integer'", name='ck_items_fat_g_integer').ddl_if(dialect='sqlite'),
    sa.CheckConstraint("typeof(protein_g) = 'integer'", name='ck_items_protein_g_integer').ddl_if(dialect='sqlite'),
    sa.CheckConstraint("typeof(quantity) = 'integer'", name='ck_items_quantity_integer').ddl_if(dialect='sqlite'),
    sa.CheckConstraint('calories >= 0', name='ck_items_calories'),
    sa.CheckConstraint('carbs_g >= 0', name='ck_items_carbs_g'),
    sa.CheckConstraint('fat_g >= 0', name='ck_items_fat_g'),
    sa.CheckConstraint('protein_g >= 0', name='ck_items_protein_g'),
    sa.CheckConstraint('quantity > 0', name='ck_items_quantity'),
    sa.ForeignKeyConstraint(['user_id', 'meal_id'], ['meals.user_id', 'meals.id'], name='fk_items_owned_meal', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_items_user_meal', 'meal_items', ['user_id', 'meal_id'], unique=False)

def downgrade():
    op.drop_index('ix_items_user_meal', table_name='meal_items')
    op.drop_table('meal_items')
    op.drop_index('ix_weights_user_occurred', table_name='weight_logs')
    op.drop_table('weight_logs')
    op.drop_index('ix_meals_user_occurred', table_name='meals')
    op.drop_table('meals')
