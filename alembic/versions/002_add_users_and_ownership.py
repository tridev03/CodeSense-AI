"""002_add_users_and_ownership

Revision ID: 002_add_users_and_ownership
Revises: 001_initial_schema
Create Date: 2026-10-02

SEC-01: Add users table (email, hashed_password, is_active, is_superuser)
SEC-02: Add user_repository_ownership table (tenant isolation join table)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_add_users_and_ownership'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(length=320), nullable=False, unique=True, index=True),
        sa.Column('hashed_password', sa.String(length=1024), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # user_repository_ownership join table
    op.create_table(
        'user_repository_ownership',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('repository_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('repositories.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_ownership_user_id', 'user_repository_ownership', ['user_id'])
    op.create_index('ix_ownership_repo_id', 'user_repository_ownership', ['repository_id'])


def downgrade() -> None:
    op.drop_table('user_repository_ownership')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
