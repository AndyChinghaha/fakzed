"""Tests for Agent session persistence and memory integration (fake model)."""

from conftest import FakeModel

from fakzed.agent import Agent
from fakzed.memory import AgenticMemory
from fakzed.model import ModelResponse
from fakzed.storage import InMemoryStorage


def test_session_persisted_and_restored() -> None:
    storage = InMemoryStorage()
    model = FakeModel()
    model.enqueue(ModelResponse(content="first answer"), ModelResponse(content="second answer"))

    agent = Agent(name="a", model=model, storage=storage, session_id="sess-1", user_id="u1")
    agent.run("hello")

    # storage now holds the session with the full run
    row = storage.read_session("sess-1")
    assert row is not None
    assert [m.content for m in row.messages if m.role == "user"] == ["hello"]
    assert [m.content for m in row.messages if m.role == "assistant"] == ["first answer"]

    # a fresh agent over the same storage resumes the conversation
    model2 = FakeModel()
    model2.enqueue(ModelResponse(content="second answer"))
    agent2 = Agent(name="a", model=model2, storage=storage, session_id="sess-1")
    result = agent2.run("follow up?")

    # the resumed agent saw the previous history
    seen = model2.calls[0]["messages"]
    contents = [m.content for m in seen]
    assert "hello" in contents
    assert "first answer" in contents
    assert result.content == "second answer"


def test_session_history_respects_num_history_runs() -> None:
    storage = InMemoryStorage()
    model = FakeModel()
    model.enqueue(ModelResponse(content="a1"), ModelResponse(content="a2"))
    agent = Agent(name="a", model=model, storage=storage, session_id="s1")
    agent.num_history_runs = 1
    agent.run("q1")
    agent.run("q2")

    seen = model.calls[1]["messages"]
    contents = [m.content for m in seen]
    # only the most recent exchange is injected
    assert "q1" not in contents
    assert "q2" in contents


def test_session_created_even_without_storage() -> None:
    """No storage: in-memory session still accumulates messages."""
    model = FakeModel()
    model.enqueue(ModelResponse(content="ok"), ModelResponse(content="ok again"))
    agent = Agent(name="a", model=model, session_id="local")
    agent.run("one")
    agent.run("two")

    assert agent.session is not None
    assert len(agent.session.messages) == 4


def test_memory_injected_into_system_prompt() -> None:
    storage = InMemoryStorage()
    memory = AgenticMemory(storage=storage, user_id="u1")
    memory.add_memory("user prefers Chinese answers", category="preferences")

    agent = Agent(name="a", model=FakeModel(), memory=memory)

    prompt = agent.get_system_prompt()

    assert "<memories>" in prompt
    assert "user prefers Chinese answers" in prompt


def test_memory_injection_can_be_disabled() -> None:
    storage = InMemoryStorage()
    memory = AgenticMemory(storage=storage, user_id="u1")
    memory.add_memory("some fact")

    agent = Agent(name="a", model=FakeModel(), memory=memory)
    agent.add_memory_to_context = False

    assert "some fact" not in (agent.get_system_prompt() or "")


def test_memory_tools_mounted() -> None:
    memory = AgenticMemory(storage=InMemoryStorage(), user_id="u1")
    agent = Agent(name="a", model=FakeModel(), memory=memory)

    names = [t.name for t in agent._all_tools()]  # noqa: SLF001

    assert "add_to_memory" in names
    assert "search_memory" in names


def test_agent_adds_memory_via_tool_loop() -> None:
    memory = AgenticMemory(storage=InMemoryStorage(), user_id="u1")
    model = FakeModel()
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[
                {
                    "id": "c1",
                    "name": "add_to_memory",
                    "arguments": {"content": "user likes cats", "category": "hobbies"},
                }
            ],  # type: ignore[arg-type]
        ),
        ModelResponse(content="Noted!"),
    )
    agent = Agent(name="a", model=model, memory=memory)

    result = agent.run("I like cats")

    assert result.content == "Noted!"
    memories = memory.search_memories()
    assert len(memories) == 1
    assert memories[0].content == "user likes cats"
    assert memories[0].category == "hobbies"
