"""Agentic memory: user-level facts shared across sessions.

Simplified retrieval for now (recency + keyword match); vector-based
semantic recall lands with the Knowledge system (phase 3.6).
"""

import uuid

from pydantic import BaseModel

from fakzed.storage import MemoryRow, Storage
from fakzed.storage.base import _now
from fakzed.tools import Tool, tool


class AgenticMemory(BaseModel):
    """Manages user-level memories backed by a `Storage` backend.

    Exposes agentic operations (add/search/update/delete) both as plain
    methods and as tools an agent can hand to the model.
    """

    storage: Storage
    user_id: str | None = None

    # -- CRUD ----------------------------------------------------------------

    def add_memory(self, content: str, category: str = "general") -> MemoryRow:
        """Persist a new memory and return it."""
        memory = MemoryRow(
            memory_id=uuid.uuid4().hex,
            content=content,
            user_id=self.user_id,
            category=category,
        )
        self.storage.add_memory(memory)
        return memory

    def search_memories(self, query: str | None = None, limit: int = 10) -> list[MemoryRow]:
        """Return recent memories, filtered by keyword match when given."""
        memories = self.storage.get_memories(user_id=self.user_id, limit=limit * 5)
        if query:
            keywords = [word.lower() for word in query.split() if len(word) > 1]
            if keywords:
                memories = [m for m in memories if any(k in m.content.lower() for k in keywords)]
        return memories[:limit]

    def update_memory(self, memory_id: str, content: str) -> MemoryRow:
        """Replace the content of an existing memory."""
        memories = self.storage.get_memories(user_id=self.user_id)
        existing = next((m for m in memories if m.memory_id == memory_id), None)
        if existing is None:
            raise ValueError(f"Memory '{memory_id}' not found")
        updated = existing.model_copy(update={"content": content})
        updated.updated_at = _now()
        self.storage.update_memory(updated)
        return updated

    def delete_memory(self, memory_id: str) -> None:
        """Remove a memory."""
        self.storage.delete_memory(memory_id)

    # -- context injection ---------------------------------------------------

    def get_memories_for_context(self, query: str | None = None, limit: int = 10) -> str:
        """Format recent memories as a prompt block for context injection."""
        memories = self.search_memories(query=query, limit=limit)
        if not memories:
            return ""
        lines = [f"- ({m.category}) {m.content}" for m in memories]
        return "<memories>\n" + "\n".join(lines) + "\n</memories>"

    # -- agent tools ---------------------------------------------------------

    def get_tools(self) -> list[Tool]:
        """Tools the agent can use to manage memories during a run."""

        @tool
        def add_to_memory(content: str, category: str = "general") -> str:
            """Remember a fact about the user. Use when the user shares a
            preference or important information worth keeping."""
            memory = self.add_memory(content, category=category)
            return f"Memory saved ({memory.memory_id[:8]}): {content}"

        @tool
        def search_memory(query: str) -> str:
            """Search the user's memories for relevant past information."""
            memories = self.search_memories(query=query)
            if not memories:
                return "No matching memories found."
            return "\n".join(f"- ({m.category}) {m.content}" for m in memories)

        return [add_to_memory, search_memory]
