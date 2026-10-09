"""Workflow primitive tests: steps, control flow, data passing, nesting."""

import asyncio
import time

import pytest
from conftest import FakeModel

from fakzed import Agent, Workflow, WorkflowContext
from fakzed.model import ModelResponse
from fakzed.workflow import IfBlock, LoopBlock, ParallelBlock, Step, WorkflowError

# -- 6.1 + 6.3: core steps and data passing -----------------------------------


def test_pipeline_collect_analyze_report() -> None:
    """M6 signature pipeline: collect -> analyze (agent) -> report."""

    def collect(input: str, ctx: WorkflowContext) -> str:
        ctx.session_data["source"] = "news api"
        return f"raw data about {input}"

    analyst_model = FakeModel()
    analyst_model.enqueue(ModelResponse(content="analysis: strong growth"))
    analyst = Agent(name="analyst", model=analyst_model)

    def report(input: str, ctx: WorkflowContext) -> str:
        return f"report: {input} (source={ctx.session_data['source']})"

    workflow = Workflow(
        name="collect-analyze-report",
        items=[
            Step(id="collect", function=collect),
            Step(id="analyze", agent=analyst, input_from="collect"),
            Step(id="report", function=report, input_from="analyze"),
        ],
    )

    result = workflow.run("fusion energy")

    assert result.content == "report: analysis: strong growth (source=news api)"
    assert result.outputs["collect"] == "raw data about fusion energy"
    assert result.outputs["analyze"] == "analysis: strong growth"
    assert result.errors == []
    # the analyst received the collector's output
    sent = analyst_model.calls[-1]["messages"][-1].content
    assert sent == "raw data about fusion energy"


def test_agent_and_team_steps() -> None:
    agent_model = FakeModel()
    agent_model.enqueue(ModelResponse(content="agent answer"))
    agent = Agent(name="worker", model=agent_model)

    workflow = Workflow(
        name="mixed",
        items=[Step(id="a", agent=agent)],
    )

    assert workflow.run("go").content == "agent answer"


# -- 6.2: control flow ---------------------------------------------------------


def test_if_block_branches_on_context() -> None:
    def add_count(input: str, ctx: WorkflowContext) -> str:
        ctx.session_data["count"] = int(input)
        return str(ctx.session_data["count"])

    def double(input: str, ctx: WorkflowContext) -> str:
        return str(ctx.session_data["count"] * 2)

    def halve(input: str, ctx: WorkflowContext) -> str:
        return str(ctx.session_data["count"] // 2)

    workflow = Workflow(
        name="branch",
        items=[
            Step(id="seed", function=add_count),
            IfBlock(
                condition=lambda ctx: ctx.session_data["count"] >= 10,
                then=[Step(id="big", function=double)],
                otherwise=[Step(id="small", function=halve)],
            ),
        ],
    )

    big = workflow.run("12")
    small = workflow.run("4")

    assert big.outputs["big"] == "24"
    assert "small" not in big.outputs
    assert small.outputs["small"] == "2"
    assert "big" not in small.outputs


def test_loop_block_runs_until_condition() -> None:
    def accumulate(input: str, ctx: WorkflowContext) -> str:
        ctx.session_data["total"] = ctx.session_data.get("total", 0) + int(input)
        return str(ctx.session_data["total"])

    workflow = Workflow(
        name="loop",
        items=[
            LoopBlock(
                steps=[Step(id="acc", function=accumulate)],
                until=lambda ctx: ctx.session_data["total"] >= 10,
                max_iterations=10,
            ),
        ],
    )

    result = workflow.run("3")

    # 3+3+3+3 = 12, stops after 4 iterations
    assert result.content == "12"


def test_loop_block_respects_max_iterations() -> None:
    calls = {"n": 0}

    def tick(input: str, ctx: WorkflowContext) -> str:
        calls["n"] += 1
        return str(calls["n"])

    workflow = Workflow(
        name="loop-max",
        items=[
            LoopBlock(
                steps=[Step(id="tick", function=tick)],
                until=lambda ctx: False,  # never satisfied
                max_iterations=3,
            ),
        ],
    )

    workflow.run("x")

    assert calls["n"] == 3


def test_parallel_block_fan_out_fan_in() -> None:
    def slow_square(input: str, ctx: WorkflowContext) -> str:
        time.sleep(0.05)
        return str(int(input) ** 2)

    def slow_cube(input: str, ctx: WorkflowContext) -> str:
        time.sleep(0.05)
        return str(int(input) ** 3)

    def join(outputs: list[str], ctx: WorkflowContext) -> str:
        return "sum=" + str(sum(int(o) for o in outputs))

    workflow = Workflow(
        name="parallel",
        items=[
            ParallelBlock(
                steps=[
                    Step(id="sq", function=slow_square),
                    Step(id="cb", function=slow_cube),
                ],
                join=join,
            ),
        ],
    )

    result = workflow.run("3")

    assert result.content == "sum=36"
    assert result.outputs["sq"] == "9"
    assert result.outputs["cb"] == "27"
    assert result.outputs["join"] == "sum=36"


# -- 6.4: nested workflows -----------------------------------------------------


def test_nested_workflow_as_step() -> None:
    def upper(input: str, ctx: WorkflowContext) -> str:
        return input.upper()

    inner = Workflow(name="inner", items=[Step(id="up", function=upper)])

    def wrap(input: str, ctx: WorkflowContext) -> str:
        return f"[{input}]"

    outer = Workflow(
        name="outer",
        items=[
            Step(id="nested", workflow=inner),
            Step(id="wrap", function=wrap, input_from="nested"),
        ],
    )

    result = outer.run("hello")

    assert result.content == "[HELLO]"
    assert result.outputs["nested"] == "HELLO"


# -- 6.5: failure handling -----------------------------------------------------


def test_step_retries_then_succeeds() -> None:
    attempts = {"n": 0}

    def flaky(input: str, ctx: WorkflowContext) -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("not yet")
        return "finally worked"

    workflow = Workflow(name="retry", items=[Step(id="f", function=flaky, retries=3)])

    result = workflow.run("go")

    assert result.content == "finally worked"
    assert attempts["n"] == 3
    assert result.errors == []


def test_step_exhausted_retries_record_error_and_continue() -> None:
    def boom(input: str, ctx: WorkflowContext) -> str:
        raise ValueError("always fails")

    def after(input: str, ctx: WorkflowContext) -> str:
        return "recovered"

    workflow = Workflow(
        name="recover",
        items=[Step(id="bad", function=boom, retries=1), Step(id="ok", function=after)],
    )

    result = workflow.run("go")

    assert result.content == "recovered"
    assert len(result.errors) == 1
    assert "always fails" in result.errors[0]
    assert result.step_results["bad"].error is not None


def test_fail_fast_raises_workflow_error() -> None:
    def boom(input: str, ctx: WorkflowContext) -> str:
        raise ValueError("fatal")

    workflow = Workflow(name="fail-fast", fail_fast=True, items=[Step(id="bad", function=boom)])

    with pytest.raises(WorkflowError, match="fatal"):
        workflow.run("go")


def test_step_timeout_is_enforced() -> None:
    def sleepy(input: str, ctx: WorkflowContext) -> str:
        time.sleep(0.5)
        return "woke up"

    workflow = Workflow(name="timeout", items=[Step(id="slow", function=sleepy, timeout=0.1)])

    result = workflow.run("go")

    assert result.content == ""
    assert result.step_results["slow"].error is not None


# -- async ---------------------------------------------------------------------


def test_arun_pipeline() -> None:
    def collect(input: str, ctx: WorkflowContext) -> str:
        return f"collected {input}"

    agent_model = FakeModel()
    agent_model.enqueue(ModelResponse(content="async analysis"))
    agent = Agent(name="analyst", model=agent_model)

    workflow = Workflow(
        name="async-pipeline",
        items=[
            Step(id="collect", function=collect),
            Step(id="analyze", agent=agent, input_from="collect"),
        ],
    )

    async def main() -> str:
        result = await workflow.arun("topic")
        return result.content

    assert asyncio.run(main()) == "async analysis"


def test_arun_parallel_block() -> None:
    def slow(input: str, ctx: WorkflowContext) -> str:
        time.sleep(0.02)
        return input + "!"

    workflow = Workflow(
        name="async-parallel",
        items=[
            ParallelBlock(
                steps=[Step(id="a", function=slow), Step(id="b", function=slow)],
            ),
        ],
    )

    async def main() -> str:
        result = await workflow.arun("x")
        return result.content

    assert asyncio.run(main()) == "x!\nx!"
