"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-02 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enums
    source_type_enum = sa.Enum('GITHUB', 'LOCAL', name='repository_source_type_enum')
    repo_status_enum = sa.Enum('PENDING', 'CLONING', 'INDEXING', 'INDEXED', 'FAILED', name='repository_status_enum')
    job_status_enum = sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', name='indexing_job_status_enum')

    # 2. repositories table
    op.create_table(
        'repositories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False, comment='Display name (GitHub slug or user-provided)'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('url', sa.String(length=2048), nullable=False, unique=True, comment='GitHub HTTPS URL or absolute local filesystem path'),
        sa.Column('source_type', source_type_enum, nullable=False),
        sa.Column('branch', sa.String(length=255), nullable=True, server_default='main'),
        sa.Column('commit_hash', sa.String(length=40), nullable=True, comment='Git commit hash of the last indexed state'),
        sa.Column('status', repo_status_enum, nullable=False, server_default='PENDING'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='Last error from indexing, if any'),
        sa.Column('file_count', sa.Integer(), nullable=True, comment='Number of files discovered during indexing'),
        sa.Column('chunk_count', sa.Integer(), nullable=True, comment='Number of chunks stored in the vector DB'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 3. indexing_jobs table
    op.create_table(
        'indexing_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('repository_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('repositories.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', job_status_enum, nullable=False, server_default='PENDING'),
        sa.Column('progress', sa.Float(), nullable=False, server_default='0.0', comment='Completion percentage 0–100'),
        sa.Column('current_step', sa.String(length=512), nullable=True, comment='Human-readable description of current step'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('files_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('files_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('chunks_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('indexing_jobs')
    op.drop_table('repositories')
    op.execute('DROP TYPE IF EXISTS indexing_job_status_enum')
    op.execute('DROP TYPE IF EXISTS repository_status_enum')
    op.execute('DROP TYPE IF EXISTS repository_source_type_enum')
