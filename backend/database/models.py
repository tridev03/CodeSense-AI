"""
SQLAlchemy ORM Models.

All models inherit from Base.
UUIDs are used as primary keys for portability in distributed systems.

UUID handling strategy:
- PostgreSQL: native UUID column type (no string overhead)
- SQLite (tests): CHAR(36) via a custom TypeDecorator
This allows the same models to power both production (PostgreSQL) and
unit tests (in-memory SQLite) without any code changes.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    CHAR,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UUID(TypeDecorator):
    """
    Platform-independent UUID type.

    Uses PostgreSQL's native UUID when connected to PostgreSQL.
    Falls back to CHAR(36) on other databases (e.g. SQLite for tests).
    Values are stored as Python uuid.UUID objects regardless of backend.
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ─── Enumerations ─────────────────────────────────────────────────────────────


class RepositoryStatus(str, PyEnum):
    """Lifecycle status of a repository registration."""
    PENDING = "pending"      # Registered, not yet indexed
    CLONING = "cloning"      # Being cloned (Phase 2)
    INDEXING = "indexing"    # Embeddings being computed (Phase 3)
    INDEXED = "indexed"      # Ready for queries
    FAILED = "failed"        # Last operation failed


class RepositorySourceType(str, PyEnum):
    GITHUB = "github"
    LOCAL = "local"


class IndexingJobStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ─── Models ───────────────────────────────────────────────────────────────────


class Repository(Base):
    """
    Represents a registered software repository.

    A repository can be indexed multiple times (e.g., after new commits).
    Each indexing attempt is tracked as an IndexingJob.
    """
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Display name (GitHub slug or user-provided)"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        unique=True,
        comment="GitHub HTTPS URL or absolute local filesystem path",
    )
    source_type: Mapped[RepositorySourceType] = mapped_column(
        Enum(RepositorySourceType, name="repository_source_type_enum"),
        nullable=False,
    )
    branch: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default="main"
    )
    commit_hash: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, comment="Git commit hash of the last indexed state"
    )
    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus, name="repository_status_enum"),
        nullable=False,
        default=RepositoryStatus.PENDING,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Last error from indexing, if any"
    )
    file_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Number of files discovered during indexing"
    )
    chunk_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Number of chunks stored in the vector DB"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    indexing_jobs: Mapped[List[IndexingJob]] = relationship(
        "IndexingJob",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="IndexingJob.created_at.desc()",
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation",
        cascade="all, delete-orphan",
        foreign_keys="Conversation.repository_id",
    )

    def __repr__(self) -> str:
        return f"<Repository id={self.id} name={self.name!r} status={self.status}>"


class IndexingJob(Base):
    """
    Tracks a single indexing run for a repository.

    Multiple jobs may exist per repository; the most recent one reflects
    the current indexing state.
    """
    __tablename__ = "indexing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[IndexingJobStatus] = mapped_column(
        Enum(IndexingJobStatus, name="indexing_job_status_enum"),
        nullable=False,
        default=IndexingJobStatus.PENDING,
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="Completion percentage 0–100"
    )
    current_step: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, comment="Human-readable description of current step"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    files_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    repository: Mapped[Repository] = relationship(
        "Repository", back_populates="indexing_jobs"
    )

    def __repr__(self) -> str:
        return (
            f"<IndexingJob id={self.id} repo={self.repository_id} "
            f"status={self.status} progress={self.progress:.1f}%>"
        )


class Conversation(Base):
    """
    Tracks a persistent conversational session (CHAT-01).
    """
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    repository_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, default="New Conversation"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at.asc()",
    )


class Message(Base):
    """
    A single chat message within a conversation.
    """
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="user"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    citations: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="JSON-serialized citations list"
    )
    model_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    tokens_used: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(
        "Conversation", back_populates="messages"
    )

