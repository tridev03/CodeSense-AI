"""
Application configuration using Pydantic Settings.

All settings are loaded from environment variables (with .env file support).
A module-level singleton `settings` is exported for application-wide use.
Sensitive values are never logged or exposed in error messages.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Knowledge Agent"
    VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    LOG_LEVEL: LogLevel = LogLevel.INFO
    SECRET_KEY: str = Field(..., min_length=32)

    # ── API ────────────────────────────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        ...,
        description="PostgreSQL connection string: postgresql://user:pass@host:port/db",
    )

    # ── Qdrant (Phase 3) ───────────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None

    # ── LLM — Groq (Phase 3) ──────────────────────────────────────────────────
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    LLM_TEMPERATURE: float = Field(default=0.1, ge=0.0, le=2.0)
    LLM_MAX_TOKENS: int = Field(default=4096, ge=256, le=32768)

    # ── Embeddings — Qwen3 (Phase 3) ──────────────────────────────────────────
    EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"
    EMBEDDING_DEVICE: str = "cuda"
    EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=512)
    # Qwen3-Embedding-0.6B produces 1024-dimensional vectors
    EMBEDDING_DIMENSION: int = 1024

    # ── Reranking — BGE (Phase 4) ──────────────────────────────────────────────
    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    RERANKER_DEVICE: str = "cuda"

    # ── Ingestion (Phase 2) ───────────────────────────────────────────────────
    GITHUB_TOKEN: Optional[str] = None
    MAX_FILE_SIZE_MB: float = Field(default=5.0, gt=0)
    MAX_REPO_SIZE_MB: float = Field(default=500.0, gt=0)
    REPOS_STORAGE_PATH: str = "./storage/repos"

    # ── Retrieval (Phase 3-4) ─────────────────────────────────────────────────
    TOP_K_RETRIEVAL: int = Field(default=20, ge=1, le=200)
    TOP_K_RERANK: int = Field(default=5, ge=1, le=50)
    RETRIEVAL_MODE: str = "hybrid"  # vector_only | bm25_only | hybrid

    # ── Langfuse (Phase 8) ────────────────────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # ── Redis / Celery (REL-01 Part 2) ────────────────────────────────────────
    # Optional — when set, the distributed Redis queue is used instead of
    # the in-process AsyncTaskWorker.  Leave empty to stay with local mode.
    REDIS_URL: Optional[str] = Field(
        default=None,
        description="Redis connection URL: redis://[:password@]host:port/db  (optional)",
    )
    CELERY_CONCURRENCY: int = Field(
        default=2,
        ge=1,
        le=32,
        description="Number of Celery worker processes per container",
    )
    CELERY_TASK_SOFT_TIMEOUT_S: int = Field(
        default=3600,
        ge=60,
        description="Soft time-limit for a single Celery task (seconds)",
    )
    CELERY_TASK_HARD_TIMEOUT_S: int = Field(
        default=7200,
        ge=60,
        description="Hard SIGKILL time-limit for a single Celery task (seconds)",
    )

    # ── Derived Properties ────────────────────────────────────────────────────

    @property
    def async_database_url(self) -> str:
        """Return database URL with asyncpg driver for SQLAlchemy async engine."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        # Already has driver specifier (e.g. sqlite+aiosqlite for tests)
        return url

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == Environment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == Environment.TESTING

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @field_validator("RETRIEVAL_MODE")
    @classmethod
    def validate_retrieval_mode(cls, v: str) -> str:
        allowed = {"vector_only", "bm25_only", "hybrid"}
        if v not in allowed:
            raise ValueError(f"RETRIEVAL_MODE must be one of {allowed}, got '{v}'")
        return v


def get_settings() -> Settings:
    """
    Factory function for Settings.

    Returns a new Settings instance. In tests, patch environment variables
    before the first import, or override the dependency in FastAPI's DI.
    """
    return Settings()


# Module-level singleton — import and use `settings` across the application.
settings: Settings = get_settings()
