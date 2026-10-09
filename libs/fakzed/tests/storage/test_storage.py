"""Tests for storage backends: InMemoryStorage and SqliteStorage."""

import pytest

from fakzed.model import Message
from fakzed.storage import InMemoryStorage, MemoryRow, SessionRow, SqliteStorage


def make_session(session_id: str = "s1") -> SessionRow:
    return SessionRow(
        session_id=session_id,
        user_id="u1",
        messages=[Message(role="user", content="hi")],
        session_data={"key": "value"},
    )


def make_memory(memory_id: str = "m1") -> MemoryRow:
    return MemoryRow(memory_id=memory_id, user_id="u1", content="likes short answers")


BACKENDS = [InMemoryStorage, SqliteStorage]


@pytest.mark.parametrize("backend_cls", BACKENDS)
def test_session_roundtrip(backend_cls, tmp_path) -> None:
    storage = (
        backend_cls()
        if backend_cls is InMemoryStorage
        else backend_cls(db_path=str(tmp_path / "test.db"))
    )
    storage.create_session(make_session())

    row = storage.read_session("s1")
    assert row is not None
    assert row.user_id == "u1"
    assert row.messages[0].content == "hi"
    assert row.session_data == {"key": "value"}


@pytest.mark.parametrize("backend_cls", BACKENDS)
def test_session_upsert_and_delete(backend_cls, tmp_path) -> None:
    storage = (
        backend_cls()
        if backend_cls is InMemoryStorage
        else backend_cls(db_path=str(tmp_path / "test.db"))
    )
    storage.create_session(make_session())

    updated = make_session()
    updated.messages.append(Message(role="assistant", content="hello"))
    storage.upsert_session(updated)

    row = storage.read_session("s1")
    assert row is not None and len(row.messages) == 2

    storage.delete_session("s1")
    assert storage.read_session("s1") is None


@pytest.mark.parametrize("backend_cls", BACKENDS)
def test_list_sessions_filters_by_user(backend_cls, tmp_path) -> None:
    storage = (
        backend_cls()
        if backend_cls is InMemoryStorage
        else backend_cls(db_path=str(tmp_path / "test.db"))
    )
    storage.create_session(make_session("s1"))
    other = make_session("s2")
    other.user_id = "u2"
    storage.create_session(other)

    assert [s.session_id for s in storage.list_sessions(user_id="u1")] == ["s1"]
    assert len(storage.list_sessions()) == 2


@pytest.mark.parametrize("backend_cls", BACKENDS)
def test_memory_crud(backend_cls, tmp_path) -> None:
    storage = (
        backend_cls()
        if backend_cls is InMemoryStorage
        else backend_cls(db_path=str(tmp_path / "test.db"))
    )
    storage.add_memory(make_memory("m1"))

    memories = storage.get_memories(user_id="u1")
    assert len(memories) == 1
    assert memories[0].content == "likes short answers"

    updated = make_memory("m1")
    updated.content = "prefers detailed answers"
    storage.update_memory(updated)
    assert storage.get_memories(user_id="u1")[0].content == "prefers detailed answers"

    storage.delete_memory("m1")
    assert storage.get_memories(user_id="u1") == []


@pytest.mark.parametrize("backend_cls", BACKENDS)
def test_memory_filters_by_user_and_limit(backend_cls, tmp_path) -> None:
    storage = (
        backend_cls()
        if backend_cls is InMemoryStorage
        else backend_cls(db_path=str(tmp_path / "test.db"))
    )
    storage.add_memory(make_memory("m1"))
    other = make_memory("m2")
    other.user_id = "u2"
    storage.add_memory(other)

    assert len(storage.get_memories(user_id="u1")) == 1
    assert len(storage.get_memories(limit=1)) == 1


def test_sqlite_persists_across_instances(tmp_path) -> None:
    db_path = str(tmp_path / "persist.db")
    storage = SqliteStorage(db_path=db_path)
    storage.create_session(make_session())
    storage.add_memory(make_memory())

    # a fresh instance over the same file sees the data
    reopened = SqliteStorage(db_path=db_path)
    assert reopened.read_session("s1") is not None
    assert len(reopened.get_memories(user_id="u1")) == 1


def test_sqlite_empty_reads(tmp_path) -> None:
    storage = SqliteStorage(db_path=str(tmp_path / "empty.db"))
    assert storage.read_session("nope") is None
    assert storage.get_memories() == []
    assert storage.list_sessions() == []
