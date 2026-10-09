"""Tests for cumulative token usage and cost tracking on Agent."""

import asyncio

import pytest
from conftest import FakeModel

from fakzed.agent.agent import Agent
from fakzed.model import ModelResponse, ToolCall, Usage
from fakzed.observability import MetricsCollector, RunObserver


def _usage(i: int, o: int) -> Usage:
    return Usage(input_tokens=i, output_tokens=o, total_tokens=i + o)


class TestCumulativeUsage:
    def test_multi_iteration_run_sums_all_calls(self) -> None:
        model = FakeModel()
        model.enqueue(
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="noop", arguments={})],
                usage=_usage(10, 5),
            ),
            ModelResponse(content="done", usage=_usage(20, 7)),
        )

        agent = Agent(name="tracker", model=model, add_state_tools=False)
        response = agent.run("go")

        assert response.usage == _usage(30, 12)
        assert agent.total_usage == _usage(30, 12)

    def test_usage_accumulates_across_runs(self) -> None:
        model = FakeModel()
        model.enqueue(
            ModelResponse(content="one", usage=_usage(10, 2)),
            ModelResponse(content="two", usage=_usage(5, 3)),
        )

        agent = Agent(name="tracker", model=model, add_state_tools=False)
        agent.run("first")
        agent.run("second")

        assert agent.total_usage == _usage(15, 5)

    def test_usage_without_usage_stays_zero(self) -> None:
        model = FakeModel()
        model.enqueue(ModelResponse(content="done"))

        agent = Agent(name="tracker", model=model, add_state_tools=False)
        agent.run("go")

        assert agent.total_usage == Usage()

    def test_reset_usage(self) -> None:
        model = FakeModel()
        model.enqueue(
            ModelResponse(content="one", usage=_usage(10, 2)),
            ModelResponse(content="two", usage=_usage(5, 3)),
        )

        agent = Agent(name="tracker", model=model, add_state_tools=False)
        agent.run("first")
        agent.reset_usage()
        agent.run("second")

        assert agent.total_usage == _usage(5, 3)

    def test_run_stream_accumulates(self) -> None:
        model = FakeModel()
        model.enqueue(
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="noop", arguments={})],
                usage=_usage(8, 1),
            ),
            ModelResponse(content="streamed", usage=_usage(9, 4)),
        )

        agent = Agent(name="tracker", model=model, add_state_tools=False)
        assert list(agent.run_stream("go"))[-1].content == "streamed"

        assert agent.total_usage == _usage(17, 5)

    def test_arun_stream_accumulates(self) -> None:
        model = FakeModel()
        model.enqueue(
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="noop", arguments={})],
                usage=_usage(3, 1),
            ),
            ModelResponse(content="async streamed", usage=_usage(4, 2)),
        )

        async def main() -> None:
            agent = Agent(name="tracker", model=model, add_state_tools=False)
            events = [event async for event in agent.arun_stream("go")]
            assert events[-1].content == "async streamed"
            assert agent.total_usage == _usage(7, 3)

        asyncio.run(main())

    def test_pause_and_resume_accumulates(self) -> None:
        model = FakeModel()
        model.enqueue(
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="noop", arguments={})],
                usage=_usage(10, 1),
            ),
            ModelResponse(content="final", usage=_usage(11, 2)),
        )

        agent = Agent(name="tracker", model=model, add_state_tools=False)
        paused = agent.run("go", stop_after_tool_call=True)
        assert paused.usage == _usage(10, 1)
        agent.resume()

        assert agent.total_usage == _usage(21, 3)


class TestCostTracking:
    def test_total_cost_from_model_id(self) -> None:
        model = FakeModel(id="gpt-4o-mini", provider="fake")
        model.enqueue(
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="noop", arguments={})],
                usage=_usage(1_000, 0),
            ),
            ModelResponse(content="done", usage=_usage(1_000, 1_000)),
        )

        agent = Agent(name="tracker", model=model, add_state_tools=False)
        agent.run("go")

        expected = (2_000 * 0.15 + 1_000 * 0.60) / 1_000_000
        assert agent.total_cost == pytest.approx(expected)

    def test_total_cost_zero_for_unknown_model(self) -> None:
        model = FakeModel(id="unknown-model", provider="fake")
        model.enqueue(
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="noop", arguments={})],
                usage=_usage(100, 0),
            ),
            ModelResponse(content="done", usage=_usage(100, 100)),
        )

        agent = Agent(name="tracker", model=model, add_state_tools=False)
        agent.run("go")

        assert agent.total_cost == 0.0

    def test_total_cost_with_string_model(self) -> None:
        agent = Agent(name="tracker", model="openai:gpt-4o-mini")
        agent._total_usage = _usage(1_000, 500)

        assert agent.total_cost == pytest.approx((1_000 * 0.15 + 500 * 0.60) / 1_000_000)

    def test_total_cost_without_model(self) -> None:
        agent = Agent(name="tracker", model=None)
        agent._total_usage = _usage(1_000, 500)

        assert agent.total_cost == 0.0

    def test_metrics_cost_usd_recorded(self) -> None:
        collector = MetricsCollector()
        model = FakeModel(id="deepseek-chat", provider="fake")
        model.enqueue(
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="noop", arguments={})],
                usage=_usage(1_000, 0),
            ),
            ModelResponse(content="done", usage=_usage(1_000, 500)),
        )

        agent = Agent(
            name="tracker",
            model=model,
            add_state_tools=False,
            observer=RunObserver(metrics=collector),
        )
        agent.run("go")

        recorded = collector.get(agent._run_id)
        assert recorded is not None
        assert recorded.cost_usd == pytest.approx((2_000 * 0.27 + 500 * 1.10) / 1_000_000)
        assert recorded.input_tokens == 2_000
        assert recorded.output_tokens == 500
        assert collector.summary().total_cost_usd == pytest.approx(recorded.cost_usd)
