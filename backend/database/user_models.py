"""
User ORM model for SEC-01/SEC-02 authentication and tenant ownership.

Adds:
  - User      — registered accounts (email + bcrypt password hash)
  - Repository.owner_id foreign key — SEC-02 tenant isolation

Alembic migration: see alembic/versions/002_add_users_and_ownership.py
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.models import Base, UUID


class User(Base):
    """
    Registered user account.

    Passwords are NEVER stored in plaintext — only the bcrypt hash.
    The 'sub' claim in JWTs equals str(user.id).
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        index=True,
        comment="User email (login identifier)",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="bcrypt hash — never plaintext"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Bypasses tenant ownership checks"
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
    repositories: Mapped[List["UserOwnedRepository"]] = relationship(
        "UserOwnedRepository",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} active={self.is_active}>"


class UserOwnedRepository(Base):
    """
    SEC-02 Tenant Ownership join table.

    Maps users to repositories they own. A repository may have exactly
    one owner (the creator). Future sharing can add extra rows per user.
    """
    __tablename__ = "user_repository_ownership"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    owner: Mapped[User] = relationship("User", back_populates="repositories")

    def __repr__(self) -> str:
        return f"<UserOwnedRepository user={self.user_id} repo={self.repository_id}>"
