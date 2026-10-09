"""SQLite storage backend: a single .db file, zero setup.

Single-instance deployments persist sessions and memories to a local file.
Multi-instance platforms switch to Postgres behind the same `Storage`
interface.
"""

import json
import sqlite3
from typing import Any

from pydantic import PrivateAttr

from fakzed.model.message import Message
from fakzed.storage.base import MemoryRow, SessionRow, Storage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    name TEXT,
    user_id TEXT,
    messages TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    session_data TEXT NOT NULL DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    user_id TEXT,
    content TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT
);
"""


class SqliteStorage(Storage):
    """File-backed storage using Python's built-in sqlite3."""

    db_path: str = "fakzed.db"
    _initialized: bool = PrivateAttr(default=False)

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            self._migrate(conn)
        self._initialized = True

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns introduced after the first schema version."""
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
        if "summary" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN summary TEXT")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _dump_messages(messages: list[Message]) -> str:
        return json.dumps([m.model_dump() for m in messages], ensure_ascii=False)

    @staticmethod
    def _load_messages(raw: str) -> list[Message]:
        return [Message(**item) for item in json.loads(raw or "[]")]

    @staticmethod
    def _dump_json(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)

    @staticmethod
    def _load_json(raw: str) -> dict[str, Any]:
        return json.loads(raw or "{}")

    # -- sessions ------------------------------------------------------------

    def create_session(self, session: SessionRow) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, name, user_id, messages, summary, session_data, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session.session_id,
                    session.name,
                    session.user_id,
                    self._dump_messages(session.messages),
                    session.summary,
                    self._dump_json(session.session_data),
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )

    def read_session(self, session_id: str) -> SessionRow | None:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return SessionRow(
            session_id=row["session_id"],
            name=row["name"],
            user_id=row["user_id"],
            messages=self._load_messages(row["messages"]),
            # _migrate guarantees the summary column exists on any schema version
            summary=row["summary"],
            session_data=self._load_json(row["session_data"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def upsert_session(self, session: SessionRow) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, name, user_id, messages, summary, session_data, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET"
                " name = excluded.name, user_id = excluded.user_id,"
                " messages = excluded.messages, summary = excluded.summary,"
                " session_data = excluded.session_data, updated_at = excluded.updated_at",
                (
                    session.session_id,
                    session.name,
                    session.user_id,
                    self._dump_messages(session.messages),
                    session.summary,
                    self._dump_json(session.session_data),
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )

    def delete_session(self, session_id: str) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def list_sessions(self, user_id: str | None = None) -> list[SessionRow]:
        self._ensure_schema()
        query = "SELECT * FROM sessions"
        params: tuple[Any, ...] = ()
        if user_id is not None:
            query += " WHERE user_id = ?"
            params = (user_id,)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            SessionRow(
                session_id=row["session_id"],
                name=row["name"],
                user_id=row["user_id"],
                messages=self._load_messages(row["messages"]),
                # _migrate guarantees the summary column exists on any schema version
                summary=row["summary"],
                session_data=self._load_json(row["session_data"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    # -- memories ------------------------------------------------------------

    def add_memory(self, memory: MemoryRow) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memories (memory_id, user_id, content, category, metadata, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    memory.memory_id,
                    memory.user_id,
                    memory.content,
                    memory.category,
                    self._dump_json(memory.metadata),
                    memory.created_at.isoformat(),
                    memory.updated_at.isoformat(),
                ),
            )

    def get_memories(self, user_id: str | None = None, limit: int | None = None) -> list[MemoryRow]:
        self._ensure_schema()
        query = "SELECT * FROM memories"
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            MemoryRow(
                memory_id=row["memory_id"],
                user_id=row["user_id"],
                content=row["content"],
                category=row["category"],
                metadata=self._load_json(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def update_memory(self, memory: MemoryRow) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                "UPDATE memories SET content = ?, category = ?, metadata = ?, updated_at = ?"
                " WHERE memory_id = ?",
                (
                    memory.content,
                    memory.category,
                    self._dump_json(memory.metadata),
                    memory.updated_at.isoformat(),
                    memory.memory_id,
                ),
            )

    def delete_memory(self, memory_id: str) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
