"""Storage abstraction: persistence backends for sessions and memories.

Backends are pluggable — `InMemoryStorage` for tests, `SqliteStorage` for
single-instance deployments, Postgres for the platform layer. Business code
only ever talks to the `Storage` interface.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from fakzed.model.message import Message


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SessionRow(BaseModel):
    """A persisted session: the full message history plus free-form state."""

    session_id: str
    name: str | None = None
    user_id: str | None = None
    messages: list[Message] = Field(default_factory=list)
    summary: str | None = None
    session_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class MemoryRow(BaseModel):
    """A persisted user-level memory shared across sessions."""

    memory_id: str
    content: str
    user_id: str | None = None
    category: str = "general"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Storage(BaseModel, ABC):
    """Persistence backend for sessions and memories."""

    # -- sessions ------------------------------------------------------------

    @abstractmethod
    def create_session(self, session: SessionRow) -> None:
        """Persist a new session."""

    @abstractmethod
    def read_session(self, session_id: str) -> SessionRow | None:
        """Load a session by id, or None if it does not exist."""

    @abstractmethod
    def upsert_session(self, session: SessionRow) -> None:
        """Create or replace a session."""

    @abstractmethod
    def delete_session(self, session_id: str) -> None:
        """Remove a session."""

    @abstractmethod
    def list_sessions(self, user_id: str | None = None) -> list[SessionRow]:
        """List sessions, optionally filtered by user."""

    # -- memories ------------------------------------------------------------

    @abstractmethod
    def add_memory(self, memory: MemoryRow) -> None:
        """Persist a new memory."""

    @abstractmethod
    def get_memories(self, user_id: str | None = None, limit: int | None = None) -> list[MemoryRow]:
        """Return memories, optionally filtered by user and capped."""

    @abstractmethod
    def update_memory(self, memory: MemoryRow) -> None:
        """Replace an existing memory."""

    @abstractmethod
    def delete_memory(self, memory_id: str) -> None:
        """Remove a memory."""
