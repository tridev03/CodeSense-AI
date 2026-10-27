"""003_add_conversations_and_messages

Revision ID: 003_add_conversations_and_messages
Revises: 002_add_users_and_ownership
Create Date: 2026-10-24

CHAT-01: Add conversations and messages tables for server-synced chat history.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003_add_conversations_and_messages'
down_revision: Union[str, None] = '002_add_users_and_ownership'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # conversations table
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=True,
            index=True,
        ),
        sa.Column(
            'repository_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('repositories.id', ondelete='CASCADE'),
            nullable=True,
            index=True,
        ),
        sa.Column('title', sa.String(length=500), nullable=False, server_default='New Conversation'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    op.create_index('ix_conversations_repo_id', 'conversations', ['repository_id'])

    # messages table
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'conversation_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('conversations.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column('role', sa.String(length=32), nullable=False, server_default='user'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('citations', sa.Text(), nullable=True),
        sa.Column('model_name', sa.String(length=128), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])


def downgrade() -> None:
    op.drop_table('messages')
    op.drop_table('conversations')

