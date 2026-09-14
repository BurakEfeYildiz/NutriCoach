"""chat"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('conversations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'id', name='uq_conversations_owner')
    )
    op.create_index('ix_conversations_user_created', 'conversations', ['user_id', 'created_at'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('conversation_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('client_request_id', sa.String(length=36), nullable=True),
    sa.Column('in_reply_to', sa.String(length=36), nullable=True),
    sa.Column('effects_committed', sa.Boolean(), nullable=False),
    sa.Column('action_results', sa.JSON(), nullable=False),
    sa.Column('error_type', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("(role = 'user' AND client_request_id IS NOT NULL AND in_reply_to IS NULL) OR (role = 'assistant' AND client_request_id IS NULL AND in_reply_to IS NOT NULL)", name='ck_messages_role_keys'),
    sa.CheckConstraint("role IN ('user', 'assistant')", name='ck_messages_role'),
    sa.CheckConstraint("status IN ('pending', 'completed', 'failed')", name='ck_messages_status'),
    sa.ForeignKeyConstraint(['user_id', 'conversation_id', 'in_reply_to'], ['messages.user_id', 'messages.conversation_id', 'messages.id'], name='fk_messages_reply_owner'),
    sa.ForeignKeyConstraint(['user_id', 'conversation_id'], ['conversations.user_id', 'conversations.id'], name='fk_messages_conversation_owner', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('in_reply_to', name='uq_messages_one_reply'),
    sa.UniqueConstraint('user_id', 'client_request_id', name='uq_messages_client_request'),
    sa.UniqueConstraint('user_id', 'conversation_id', 'id', name='uq_messages_conversation_owner'),
    sa.UniqueConstraint('user_id', 'id', name='uq_messages_owner')
    )
    op.create_index('ix_messages_user_conversation_created', 'messages', ['user_id', 'conversation_id', 'created_at'], unique=False)
    op.create_table('ai_requests',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('message_id', sa.String(length=36), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('phase', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('total_tokens', sa.Integer(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('error_type', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("phase IN ('intent', 'coach')", name='ck_ai_requests_phase'),
    sa.CheckConstraint("status IN ('pending', 'completed', 'failed')", name='ck_ai_requests_status'),
    sa.CheckConstraint('input_tokens IS NULL OR input_tokens >= 0', name='ck_ai_requests_input_tokens'),
    sa.CheckConstraint('latency_ms IS NULL OR latency_ms >= 0', name='ck_ai_requests_latency_ms'),
    sa.CheckConstraint('output_tokens IS NULL OR output_tokens >= 0', name='ck_ai_requests_output_tokens'),
    sa.CheckConstraint('total_tokens IS NULL OR total_tokens >= 0', name='ck_ai_requests_total_tokens'),
    sa.ForeignKeyConstraint(['user_id', 'message_id'], ['messages.user_id', 'messages.id'], name='fk_ai_requests_message_owner', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_requests_user_created', 'ai_requests', ['user_id', 'created_at'], unique=False)

def downgrade():
    op.drop_index('ix_ai_requests_user_created', table_name='ai_requests')
    op.drop_table('ai_requests')
    op.drop_index('ix_messages_user_conversation_created', table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_conversations_user_created', table_name='conversations')
    op.drop_table('conversations')
