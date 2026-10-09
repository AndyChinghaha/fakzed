"""In-memory storage backend (tests and ephemeral sessions)."""

from pydantic import Field

from fakzed.storage.base import MemoryRow, SessionRow, Storage


class InMemoryStorage(Storage):
    """Dict-backed storage; data lives for the lifetime of the instance."""

    sessions: dict[str, SessionRow] = Field(default_factory=dict)
    memories: dict[str, MemoryRow] = Field(default_factory=dict)

    # -- sessions ------------------------------------------------------------

    def create_session(self, session: SessionRow) -> None:
        self.sessions[session.session_id] = session

    def read_session(self, session_id: str) -> SessionRow | None:
        return self.sessions.get(session_id)

    def upsert_session(self, session: SessionRow) -> None:
        self.sessions[session.session_id] = session

    def delete_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def list_sessions(self, user_id: str | None = None) -> list[SessionRow]:
        sessions = list(self.sessions.values())
        if user_id is not None:
            sessions = [s for s in sessions if s.user_id == user_id]
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    # -- memories ------------------------------------------------------------

    def add_memory(self, memory: MemoryRow) -> None:
        self.memories[memory.memory_id] = memory

    def get_memories(self, user_id: str | None = None, limit: int | None = None) -> list[MemoryRow]:
        memories = list(self.memories.values())
        if user_id is not None:
            memories = [m for m in memories if m.user_id == user_id]
        memories = sorted(memories, key=lambda m: m.updated_at, reverse=True)
        if limit is not None:
            memories = memories[:limit]
        return memories

    def update_memory(self, memory: MemoryRow) -> None:
        self.memories[memory.memory_id] = memory

    def delete_memory(self, memory_id: str) -> None:
        self.memories.pop(memory_id, None)
