"""Tests for the Agent primitive and its run loop (fake model)."""

import asyncio

import pytest
from conftest import FakeModel
from pydantic import BaseModel

from fakzed.agent import Agent, AgentMaxIterationsError
from fakzed.model import Message, ModelResponse, ToolCall
from fakzed.tools import Tool, tool


def make_agent(model: FakeModel) -> Agent:
    return Agent(name="test agent", description="a helper", model=model)


class Quote(BaseModel):
    text: str
    author: str


def test_simple_run() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="Hello there!"))
    agent = make_agent(model)

    result = agent.run("Hi")

    assert result.content == "Hello there!"
    assert result.event == "complete"
    # system + user + assistant
    roles = [m.role for m in result.messages]
    assert roles == ["system", "user", "assistant"]
    assert result.messages[0].content == "You are test agent: a helper"


def test_run_accepts_message_object() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="ok"))
    agent = make_agent(model)

    result = agent.run(Message(role="user", content="ping"))

    assert result.messages[1].role == "user"
    assert result.messages[1].content == "ping"


def test_system_prompt_from_instructions() -> None:
    agent = Agent(
        name="coder",
        instructions=["Always write tests.", "Prefer clarity."],
        model=FakeModel(),
    )
    prompt = agent.get_system_prompt()
    assert "You are coder" in prompt
    assert "Always write tests." in prompt
    assert "Prefer clarity." in prompt


def test_no_system_prompt_when_unconfigured() -> None:
    agent = Agent(model=FakeModel())
    assert agent.get_system_prompt() is None


def test_tool_loop_executes_and_finalizes() -> None:
    calls: list[dict] = []

    @tool
    def get_weather(city: str) -> str:
        """Return the weather for a city."""
        calls.append({"city": city})
        return f"sunny in {city}"

    model = FakeModel()
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="call_1", name="get_weather", arguments={"city": "Beijing"})],
        ),
        ModelResponse(content="It is sunny in Beijing."),
    )
    agent = Agent(name="weather", tools=[get_weather], model=model)

    result = agent.run("What's the weather?")

    assert calls == [{"city": "Beijing"}]
    assert result.content == "It is sunny in Beijing."
    roles = [m.role for m in result.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    assert result.messages[3].content == "sunny in Beijing"
    # the model received the tool schema
    sent_tools = model.calls[0]["tools"]
    assert sent_tools is not None and sent_tools[0].name == "get_weather"


def test_unknown_tool_returns_error_to_model() -> None:
    model = FakeModel()
    model.enqueue(
        ModelResponse(content="", tool_calls=[ToolCall(id="c1", name="nope", arguments={})]),
        ModelResponse(content="Tool failed, I'll improvise."),
    )
    agent = make_agent(model)

    result = agent.run("do the thing")

    assert "Error: unknown tool 'nope'" in result.messages[3].content
    assert result.content == "Tool failed, I'll improvise."


def test_tool_exception_is_reported() -> None:
    @tool
    def broken() -> str:
        """Always fails."""
        raise RuntimeError("boom")

    model = FakeModel()
    model.enqueue(
        ModelResponse(content="", tool_calls=[ToolCall(id="c1", name="broken", arguments={})]),
        ModelResponse(content="Recovered."),
    )
    agent = Agent(name="a", tools=[broken], model=model)

    result = agent.run("go")

    assert "RuntimeError: boom" in result.messages[3].content


def test_max_iterations_raises() -> None:
    model = FakeModel()
    model.enqueue(
        ModelResponse(content="", tool_calls=[ToolCall(id="c1", name="loop", arguments={})]),
        ModelResponse(content="", tool_calls=[ToolCall(id="c2", name="loop", arguments={})]),
    )
    agent = Agent(name="looper", tools=[Tool(name="loop", entrypoint=lambda: "x")], model=model)
    agent.max_iterations = 2

    with pytest.raises(AgentMaxIterationsError):
        agent.run("start")


def test_structured_output_passthrough() -> None:
    model = FakeModel()
    model.enqueue(
        ModelResponse(
            content='{"text": "hi", "author": "me"}', parsed=Quote(text="hi", author="me")
        )
    )
    agent = make_agent(model)

    result = agent.run("quote", response_format=Quote)

    assert isinstance(result.parsed, Quote)
    assert result.parsed.text == "hi"


def test_history_injection() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="first"), ModelResponse(content="second"))
    agent = make_agent(model)
    agent.add_history_to_context = True

    agent.run("one")
    result = agent.run("two")

    # second call sees the previous run's user+assistant messages
    seen = model.calls[1]["messages"]
    contents = [m.content for m in seen]
    assert "one" in contents
    assert "first" in contents
    assert result.content == "second"


def test_run_stream_events() -> None:
    model = FakeModel()
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="calc", arguments={"expr": "1+1"})],
        ),
        ModelResponse(content="The answer is 2."),
    )
    agent = Agent(name="math", tools=[Tool(name="calc", entrypoint=lambda expr: "2")], model=model)

    events = list(agent.run_stream("calculate"))

    kinds = [e.event for e in events]
    assert kinds == ["chunk", "tool_call_completed", "chunk", "complete"]
    assert events[1].tool_call is not None
    assert events[1].tool_call.name == "calc"
    assert events[1].tool_call_result == "2"
    assert events[-1].content == "The answer is 2."


def test_arun_matches_run() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="async hello"))
    agent = make_agent(model)

    result = asyncio.run(agent.arun("hi"))

    assert result.content == "async hello"


def test_arun_stream_events() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="streamed"))
    agent = make_agent(model)

    async def collect() -> list[str]:
        return [e.event async for e in agent.arun_stream("hi")]

    assert asyncio.run(collect()) == ["chunk", "complete"]


def test_print_response(capsys: pytest.CaptureFixture[str]) -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="printed"))
    agent = make_agent(model)

    agent.print_response("show me")

    out = capsys.readouterr().out
    assert "show me" in out
    assert "printed" in out


def test_print_response_stream(capsys: pytest.CaptureFixture[str]) -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="streamed output"))
    agent = make_agent(model)

    agent.print_response("stream", stream=True)

    assert "streamed output" in capsys.readouterr().out
