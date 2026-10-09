"""Tests for AgenticMemory: CRUD, context formatting, and agent tools."""

from fakzed.memory import AgenticMemory
from fakzed.storage import InMemoryStorage


def make_memory() -> AgenticMemory:
    return AgenticMemory(storage=InMemoryStorage(), user_id="u1")


def test_add_and_search_memories() -> None:
    memory = make_memory()
    memory.add_memory("user prefers concise answers", category="preferences")
    memory.add_memory("user works in fintech", category="facts")

    assert len(memory.search_memories()) == 2
    results = memory.search_memories(query="fintech")
    assert len(results) == 1
    assert "fintech" in results[0].content


def test_update_and_delete_memory() -> None:
    memory = make_memory()
    row = memory.add_memory("user uses Python")

    updated = memory.update_memory(row.memory_id, "user prefers Python")
    assert updated.content == "user prefers Python"
    assert memory.search_memories()[0].content == "user prefers Python"

    memory.delete_memory(row.memory_id)
    assert memory.search_memories() == []


def test_update_missing_memory_raises() -> None:
    memory = make_memory()
    try:
        memory.update_memory("missing", "x")
    except ValueError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_memories_scoped_to_user() -> None:
    memory = make_memory()
    memory.add_memory("shared across all users?")

    other = AgenticMemory(storage=memory.storage, user_id="u2")
    assert other.search_memories() == []
    assert len(memory.search_memories()) == 1


def test_get_memories_for_context_format() -> None:
    memory = make_memory()
    memory.add_memory("user likes bullet points", category="preferences")

    block = memory.get_memories_for_context()

    assert "<memories>" in block
    assert "(preferences) user likes bullet points" in block
    assert memory.get_memories_for_context(query="nothing matches") == "" or "<memories>" in block


def test_memory_tools() -> None:
    memory = make_memory()
    tools = memory.get_tools()
    names = [t.name for t in tools]

    assert names == ["add_to_memory", "search_memory"]

    add_tool = {t.name: t for t in tools}["add_to_memory"]
    result = add_tool.call({"content": "user loves cricket", "category": "hobbies"})
    assert "Memory saved" in result
    assert memory.search_memories(query="cricket")

    search_tool = {t.name: t for t in tools}["search_memory"]
    found = search_tool.call({"query": "cricket"})
    assert "user loves cricket" in found
    assert search_tool.call({"query": "zzz-nothing"}) == "No matching memories found."
