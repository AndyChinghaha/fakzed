"""Phase 7 tests: guardrails, hooks, and human-in-the-loop."""

import asyncio

import pytest
from conftest import FakeModel

from fakzed import Agent, GuardrailError, Hooks, InputGuardrail, OutputGuardrail
from fakzed.model import ModelResponse, ToolCall
from fakzed.tools import tool

# -- 7.1 guardrails ------------------------------------------------------------


def test_input_guardrail_blocks_run() -> None:
    model = FakeModel()
    agent = Agent(
        name="guarded",
        model=model,
        input_guardrails=[
            InputGuardrail(
                name="no politics",
                check=lambda data, ctx: "politics" not in data,
            )
        ],
    )

    with pytest.raises(GuardrailError, match="no politics"):
        agent.run("tell me about politics")

    # the model was never called
    assert model.calls == []


def test_input_guardrail_accepts_string_rejection_reason() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="ok"))
    agent = Agent(
        name="guarded",
        model=model,
        input_guardrails=[
            InputGuardrail(
                name="length", check=lambda data, ctx: "too long" if len(data) > 10 else ""
            )
        ],
    )

    with pytest.raises(GuardrailError, match="too long"):
        agent.run("this message is definitely too long")

    assert agent.run("short").content == "ok"


def test_output_guardrail_triggers_model_revision() -> None:
    model = FakeModel()
    model.enqueue(
        ModelResponse(content="the secret is 42"),  # blocked
        ModelResponse(content="I cannot reveal that"),  # revised
    )
    agent = Agent(
        name="guarded",
        model=model,
        output_guardrails=[
            OutputGuardrail(name="no secrets", check=lambda data, ctx: "42" not in data)
        ],
    )

    response = agent.run("what is the answer?")

    assert response.content == "I cannot reveal that"
    # the model saw the guardrail feedback before revising
    feedback = model.calls[1]["messages"][-1].content
    assert "no secrets" in feedback


def test_output_guardrail_retries_exhausted_returns_last_answer() -> None:
    model = FakeModel()
    model.enqueue(
        ModelResponse(content="42"),
        ModelResponse(content="still 42"),
        ModelResponse(content="42 again"),
    )
    agent = Agent(
        name="guarded",
        model=model,
        output_guardrails=[
            OutputGuardrail(name="no numbers", check=lambda data, ctx: "42" not in data, retries=2)
        ],
    )

    response = agent.run("answer")

    # after 2 revision attempts the last answer is returned
    assert response.content == "42 again"
    assert len(model.calls) == 3


def test_output_guardrail_passes_clean_answer() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="clean answer"))
    agent = Agent(
        name="guarded",
        model=model,
        output_guardrails=[
            OutputGuardrail(name="no banned", check=lambda data, ctx: "banned" not in data)
        ],
    )

    assert agent.run("hi").content == "clean answer"
    assert len(model.calls) == 1


# -- 7.2 hooks ------------------------------------------------------------------


def test_hooks_fire_on_run_and_tool_calls() -> None:
    events: list[str] = []

    @tool
    def lookup(query: str) -> str:
        """Look something up."""
        return f"result for {query}"

    model = FakeModel()
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="lookup", arguments={"query": "x"})],
        ),
        ModelResponse(content="done"),
    )
    agent = Agent(
        name="hooked",
        model=model,
        tools=[lookup],
        hooks=Hooks(
            on_run_start=[lambda msg: events.append(f"start:{msg}")],
            on_run_end=[lambda resp: events.append(f"end:{resp.content}")],
            on_tool_call=[lambda call: events.append(f"call:{call.name}")],
            on_tool_result=[lambda call, result: events.append(f"result:{result}")],
        ),
    )

    agent.run("hello")

    assert events == [
        "start:hello",
        "call:lookup",
        "result:result for x",
        "end:done",
    ]


def test_hook_errors_do_not_break_the_run() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="survived"))

    def bad_hook(_: str) -> None:
        raise RuntimeError("hook bug")

    agent = Agent(
        name="hooked",
        model=model,
        hooks=Hooks(on_run_start=[bad_hook]),
    )

    assert agent.run("hi").content == "survived"


# -- 7.3 human-in-the-loop -------------------------------------------------------


def test_stop_after_tool_call_and_resume() -> None:
    calls: list[str] = []

    @tool
    def fetch(query: str) -> str:
        """Fetch data (simulated)."""
        calls.append(query)
        return f"data for {query}"

    model = FakeModel()
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="fetch", arguments={"query": "alpha"})],
        ),
        ModelResponse(content="final answer"),
    )
    agent = Agent(name="pausable", model=model, tools=[fetch])

    paused = agent.run("go", stop_after_tool_call=True)

    # the tool ran, the loop paused before the next model call
    assert paused.event == "paused"
    assert paused.tool_call is not None and paused.tool_call.name == "fetch"
    assert paused.tool_call_result == "data for alpha"
    assert calls == ["alpha"]
    assert len(model.calls) == 1

    completed = agent.resume()

    assert completed.event == "complete"
    assert completed.content == "final answer"
    assert len(model.calls) == 2


def test_resume_without_pause_raises() -> None:
    agent = Agent(name="x", model=FakeModel())

    with pytest.raises(ValueError, match="No paused run"):
        agent.resume()


def test_arun_stop_after_tool_call_and_aresume() -> None:
    @tool
    def fetch(query: str) -> str:
        """Fetch data."""
        return f"async data for {query}"

    model = FakeModel()
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="fetch", arguments={"query": "beta"})],
        ),
        ModelResponse(content="async final"),
    )
    agent = Agent(name="pausable", model=model, tools=[fetch])

    async def main() -> tuple[str, str]:
        paused = await agent.arun("go", stop_after_tool_call=True)
        completed = await agent.aresume()
        return paused.event, completed.content

    paused_event, final_content = asyncio.run(main())
    assert paused_event == "paused"
    assert final_content == "async final"


def test_guardrails_and_hitl_compose() -> None:
    """Paused runs keep guardrail state: input checked once, output after resume."""
    model = FakeModel()
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="fetch", arguments={"query": "x"})],
        ),
        ModelResponse(content="clean final"),
    )

    @tool
    def fetch(query: str) -> str:
        """Fetch."""
        return "data"

    agent = Agent(
        name="composed",
        model=model,
        tools=[fetch],
        output_guardrails=[
            OutputGuardrail(name="clean", check=lambda data, ctx: "banned" not in data)
        ],
    )

    paused = agent.run("start", stop_after_tool_call=True)
    assert paused.event == "paused"
    completed = agent.resume()
    assert completed.content == "clean final"
