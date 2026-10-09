"""Async paths and edge branches for Agent / Team / Workflow / Embedder / Anthropic."""

import asyncio
import sys
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import FakeModel
from pydantic import BaseModel

from fakzed.agent import Agent, Team
from fakzed.guardrails import OutputGuardrail
from fakzed.knowledge.embedder import OpenAIEmbedder
from fakzed.model import Message, ModelResponse, ToolCall
from fakzed.model.provider import AnthropicChat
from fakzed.tools import tool
from fakzed.workflow import (
    IfBlock,
    LoopBlock,
    ParallelBlock,
    Step,
    Workflow,
    WorkflowError,
)

# -- Agent async tool loop -----------------------------------------------------


def test_agent_arun_stream_tool_loop() -> None:
    async def main() -> None:
        @tool
        async def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        model = FakeModel()
        model.enqueue(
            ModelResponse(
                content="", tool_calls=[ToolCall(id="c1", name="add", arguments={"a": 1, "b": 2})]
            ),
            ModelResponse(content="3", event="complete"),
        )
        agent = Agent(name="calc", model=model, tools=[add])

        events = [e async for e in agent.arun_stream("1 + 2")]

        assert any(e.event == "tool_call_completed" for e in events)
        assert events[-1].content == "3"
        # assistant tool_calls message + tool result message were appended
        roles = [m.role for m in events[-1].messages]
        assert roles.count("tool") == 1

    asyncio.run(main())


def test_agent_arun_stream_output_guardrail_retry() -> None:
    async def main() -> None:
        calls: list[str] = []

        def check_no_placeholder(content: str, ctx: dict[str, Any] | None) -> str | None:
            calls.append(content)
            return "placeholder detected" if "PLACEHOLDER" in content else None

        model = FakeModel()
        model.enqueue(
            ModelResponse(content="PLACEHOLDER answer", event="complete"),
            ModelResponse(content="final answer", event="complete"),
        )
        agent = Agent(
            name="safe",
            model=model,
            output_guardrails=[
                OutputGuardrail(name="no-ph", check=check_no_placeholder, retries=2)
            ],
        )

        events = [e async for e in agent.arun_stream("q")]

        assert events[-1].content == "final answer"
        assert len(calls) == 2

    asyncio.run(main())


def test_print_response_with_markdown(capsys: Any) -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="**bold** text"))
    agent = Agent(name="md", model=model, markdown=True)

    agent.print_response("hi")

    captured = capsys.readouterr()
    assert "bold" in captured.out
    assert "hi" in captured.out


# -- Team async paths ----------------------------------------------------------


def test_team_arun_stream_coordinate() -> None:
    async def main() -> None:
        model = FakeModel()
        model.enqueue(ModelResponse(content="coordinated", event="complete"))
        team = Team(name="t", model=model)

        events = [e async for e in team.arun_stream("hello")]

        assert events[-1].content == "coordinated"

    asyncio.run(main())


def test_team_resolve_route_dict_and_invalid() -> None:

    ok = ModelResponse(content="", parsed={"member": "m1", "task": "do it"})
    route = Team._resolve_route(ok)
    assert route is not None and route.member == "m1" and route.task == "do it"

    bad = ModelResponse(content="", parsed={"member": "m1"})  # missing task
    assert Team._resolve_route(bad) is None


def test_team_arun_route_failures() -> None:
    async def main() -> None:
        member = Agent(name="member", model=FakeModel())
        team = Team(name="router", mode="route", members=[member], model=FakeModel())

        # leader returns no route
        model = FakeModel()
        model.enqueue(ModelResponse(content="", parsed=None))
        team.model = model
        result = await team._arun_route(Message(role="user", content="hi"), None)  # noqa: SLF001
        assert "Team route failed" in result.content

        # leader routes to an unknown member
        model = FakeModel()
        model.enqueue(ModelResponse(content="", parsed={"member": "ghost", "task": "x"}))
        team.model = model
        result = await team._arun_route(Message(role="user", content="hi"), None)  # noqa: SLF001
        assert "unknown member" in result.content

    asyncio.run(main())


# -- Workflow async paths ------------------------------------------------------


def test_workflow_arun_blocks_and_join() -> None:
    async def main() -> None:
        def inc(input: str, ctx: Any) -> int:
            return len(input)

        async def double(input: str, ctx: Any) -> int:
            return len(input) * 2

        workflow = Workflow(
            name="w",
            items=[
                Step(id="start", function=inc),
                IfBlock(
                    condition=lambda ctx: True,
                    then=[Step(id="then", function=inc)],
                    otherwise=[Step(id="else", function=inc)],
                ),
                LoopBlock(
                    steps=[Step(id="tick", function=inc)],
                    until=lambda ctx: True,
                    max_iterations=5,
                ),
                ParallelBlock(
                    steps=[Step(id="a", function=inc), Step(id="b", function=double)],
                    join=lambda outputs, ctx: sum(int(o) for o in outputs),
                ),
            ],
        )

        result = await workflow.arun("abc")

        # parallel join result lands in outputs (parallel steps are not StepResults)
        assert result.outputs["join"] is not None
        assert result.outputs["a"] is not None
        assert result.outputs["b"] is not None

    asyncio.run(main())


def test_workflow_arun_fail_fast() -> None:
    async def main() -> None:
        def boom(input: str, ctx: Any) -> str:
            raise ValueError("boom")

        workflow = Workflow(name="w", fail_fast=True, items=[Step(id="bad", function=boom)])

        with pytest.raises(WorkflowError, match="boom"):
            await workflow.arun("go")

    asyncio.run(main())


def test_workflow_arun_swallows_errors_when_not_fail_fast() -> None:
    async def main() -> None:
        def boom(input: str, ctx: Any) -> str:
            raise ValueError("boom")

        def ok(input: str, ctx: Any) -> str:
            return "ok"

        workflow = Workflow(
            name="w", items=[Step(id="bad", function=boom), Step(id="good", function=ok)]
        )

        result = await workflow.arun("go")

        assert result.step_results["bad"].error is not None
        assert result.step_results["good"].output == "ok"

    asyncio.run(main())


# -- Embedder / Anthropic edges ------------------------------------------------


def test_openai_embedder_embed_and_client(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class _Embeddings:
        def __init__(self, client: Any) -> None:
            self._client = client

        def create(self, **kwargs: Any) -> Any:
            captured["kwargs"] = kwargs
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])

    class _OpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs
            self.embeddings = _Embeddings(self)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "env-k")

    embedder = OpenAIEmbedder(base_url="http://b")
    assert embedder.get_api_key() == "env-k"

    vectors = embedder.embed(["hello"])

    assert vectors == [[0.1, 0.2]]
    assert captured["client"]["api_key"] == "env-k"
    assert captured["kwargs"]["model"] == "text-embedding-3-small"


def test_anthropic_sync_stream_reasoning_and_structured() -> None:
    class _Ans(BaseModel):
        ok: bool

    events = [
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="thinking_delta", thinking="th"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text='{"ok":'),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text="true}"),
        ),
    ]
    model = AnthropicChat(id="claude", api_key="k")

    class _CtxList:
        def __init__(self, events: list[Any]) -> None:
            self._events = events

        def __enter__(self) -> list[Any]:
            return self._events

        def __exit__(self, *exc: Any) -> bool:
            return False

    class _Fake:
        def __init__(self) -> None:
            self.kwargs: dict[str, Any] = {}
            self.messages = SimpleNamespace(stream=self._stream)

        def _stream(self, **kwargs: Any) -> _CtxList:
            self.kwargs = kwargs
            return _CtxList(events)

    model._client = _Fake()  # noqa: SLF001

    out = list(model.response_stream([Message(role="user", content="q")], response_format=_Ans))

    assert out[-1].event == "complete"
    assert out[-1].reasoning_content == "th"
    assert out[-1].parsed is not None and out[-1].parsed.ok is True
