"""memory"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('memories',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('category', sa.String(length=40), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('source_message_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='ck_memories_confidence'),
        sa.CheckConstraint("status IN ('active', 'superseded', 'deleted')", name='ck_memories_status'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id', 'source_message_id'], ['messages.user_id', 'messages.id'], name='fk_memories_source_message', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'id', name='uq_memories_owner'),
    )
    op.create_index('ix_memories_user_category', 'memories', ['user_id', 'category'], unique=False)
    op.create_index('ix_memories_user_key', 'memories', ['user_id', 'key'], unique=False)
    op.create_index('ix_memories_user_status', 'memories', ['user_id', 'status'], unique=False)


def downgrade():
    op.drop_index('ix_memories_user_status', table_name='memories')
    op.drop_index('ix_memories_user_key', table_name='memories')
    op.drop_index('ix_memories_user_category', table_name='memories')
    op.drop_table('memories')
