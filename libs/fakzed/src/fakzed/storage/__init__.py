"""Storage system: pluggable persistence backends (memory, sqlite, postgres...)."""

from fakzed.storage.base import MemoryRow, SessionRow, Storage
from fakzed.storage.memory import InMemoryStorage
from fakzed.storage.sqlite import SqliteStorage

__all__ = ["Storage", "SessionRow", "MemoryRow", "InMemoryStorage", "SqliteStorage"]
