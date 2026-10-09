"""Session: a persistent conversation thread with free-form state."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from fakzed.model.message import Message
from fakzed.storage.base import SessionRow, _now


class Session(BaseModel):
    """A conversation thread: id, owner, message history, and session state.

    Sessions survive restarts when paired with a `Storage` backend. The agent
    loads the session on `run` and persists the updated history afterwards.
    """

    session_id: str
    name: str | None = None
    user_id: str | None = None
    messages: list[Message] = Field(default_factory=list)
    summary: str | None = None
    session_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def add_message(self, message: Message) -> None:
        """Append a message and bump the updated timestamp."""
        self.messages.append(message)
        self.updated_at = _now()

    def to_row(self) -> SessionRow:
        """Convert to the storage row shape."""
        return SessionRow(
            session_id=self.session_id,
            name=self.name,
            user_id=self.user_id,
            messages=self.messages,
            summary=self.summary,
            session_data=self.session_data,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_row(cls, row: SessionRow) -> "Session":
        """Build a session from a storage row."""
        return cls(
            session_id=row.session_id,
            name=row.name,
            user_id=row.user_id,
            messages=row.messages,
            summary=row.summary,
            session_data=row.session_data,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
