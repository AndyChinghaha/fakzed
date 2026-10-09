"""Workflow primitive: deterministic orchestration of steps.

A workflow chains Agents, Teams, plain functions, and nested workflows into
a deterministic pipeline, in contrast to the model-driven freedom of an
Agent run.
"""

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from fakzed.agent.agent import Agent
from fakzed.model import Usage
from fakzed.observability import RunEvent, RunObserver

#: A plain-function step: receives the step input and the shared context.
StepFunction = Callable[[str, "WorkflowContext"], str]
#: Condition used by if/loop blocks: inspects the shared context.
Condition = Callable[["WorkflowContext"], bool]


class WorkflowContext(BaseModel):
    """Shared state flowing through a workflow run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    workflow_id: str
    #: Free-form data shared across steps (steps may read and write).
    session_data: dict[str, Any] = Field(default_factory=dict)
    #: Output of every completed step, keyed by step id.
    step_outputs: dict[str, str] = Field(default_factory=dict)


class StepResult(BaseModel):
    """Outcome of a single step."""

    step_id: str
    output: str = ""
    error: str | None = None
    attempts: int = 1
    elapsed_seconds: float = 0.0


class WorkflowResult(BaseModel):
    """Outcome of a workflow run."""

    content: str = ""
    outputs: dict[str, str] = Field(default_factory=dict)
    step_results: dict[str, StepResult] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    usage: Usage | None = None


class WorkflowError(Exception):
    """Raised when a workflow fails with `fail_fast` enabled."""


class Step(BaseModel):
    """One unit of work: an agent run, a function call, or a nested workflow.

    The step input defaults to the workflow's initial input; set `input_from`
    to feed the output of an earlier step instead.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    agent: Agent | None = None
    function: StepFunction | None = None
    workflow: "Workflow | None" = None
    input_from: str | None = None
    retries: int = 0
    timeout: float | None = None

    def execute(
        self,
        workflow: "Workflow",
        context: WorkflowContext,
        default_input: str,
    ) -> str:
        """Resolve the input and run the step body."""
        step_input = default_input
        if self.input_from is not None:
            step_input = context.step_outputs.get(self.input_from, "")
        if self.agent is not None:
            return self.agent.run(step_input).content
        if self.function is not None:
            result = self.function(step_input, context)
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            return str(result)
        if self.workflow is not None:
            return self.workflow.run(step_input).content
        raise ValueError(f"Step '{self.id}' has no agent, function, or workflow")


class IfBlock(BaseModel):
    """Conditional branch: run `then` or `otherwise` based on context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    condition: Condition
    then: list[Step] = Field(default_factory=list)
    otherwise: list[Step] = Field(default_factory=list)


class LoopBlock(BaseModel):
    """Repeat steps until a condition on the context holds."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    steps: list[Step] = Field(default_factory=list)
    until: Condition | None = None
    max_iterations: int = 5


class ParallelBlock(BaseModel):
    """Fan-out: run steps concurrently, then fan-in through `join`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    steps: list[Step] = Field(default_factory=list)
    #: Fan-in: combines the member outputs (in step order) into one answer.
    join: Callable[[list[str], WorkflowContext], str] | None = None


WorkflowItem = Step | IfBlock | LoopBlock | ParallelBlock


class Workflow(BaseModel):
    """Deterministic orchestration of steps, branches, loops, and parallelism.

    Example:
        workflow = Workflow(
            name="collect-analyze-report",
            items=[
                Step(id="collect", function=collect_data),
                Step(id="analyze", agent=analyst, input_from="collect"),
                Step(id="report", function=write_report, input_from="analyze"),
            ],
        )
        result = workflow.run("latest fusion energy news")
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str | None = None
    description: str | None = None
    items: list[WorkflowItem] = Field(default_factory=list)
    #: Abort the whole run on the first step failure instead of recording it.
    fail_fast: bool = False
    #: Step-level hook fired after each step finishes (success or failure).
    on_step_complete: Callable[[StepResult], None] | None = None
    #: Observability backends; step events are published to its event bus.
    observer: RunObserver | None = None

    #: Accumulated results of the last run (for inspection and replay).
    last_result: WorkflowResult | None = Field(default=None, exclude=True)

    # -- execution -----------------------------------------------------------

    def run(self, input: str | None = None) -> WorkflowResult:
        """Run all items in order and return the aggregated result."""
        self._reset_run_state()
        context = WorkflowContext(workflow_id=self.name or "workflow")
        try:
            output = self._run_items(self.items, context, input or "")
        except WorkflowError as exc:
            raise exc
        self.last_result = WorkflowResult(
            content=output,
            outputs=dict(context.step_outputs),
            step_results=self._step_results,
            errors=self._errors,
        )
        return self.last_result

    #: Per-run step results, keyed by step id.
    _step_results: dict[str, StepResult] = PrivateAttr(default_factory=dict)
    _errors: list[str] = PrivateAttr(default_factory=list)

    def _reset_run_state(self) -> None:
        self._step_results = {}
        self._errors = []

    def _run_items(
        self, items: Sequence[WorkflowItem], context: WorkflowContext, default_input: str
    ) -> str:
        """Run items in sequence; returns the output of the last item."""
        last_output = default_input
        for item in items:
            if isinstance(item, Step):
                last_output = self._run_step(item, context, default_input)
            elif isinstance(item, IfBlock):
                branch = item.then if item.condition(context) else item.otherwise
                if branch:
                    last_output = self._run_items(branch, context, default_input)
            elif isinstance(item, LoopBlock):
                last_output = self._run_loop(item, context, default_input)
            elif isinstance(item, ParallelBlock):
                last_output = self._run_parallel(item, context, default_input)
        return last_output

    def _run_step(self, step: Step, context: WorkflowContext, default_input: str) -> str:
        import time

        attempts = 0
        while True:
            attempts += 1
            started = time.monotonic()
            try:
                if step.timeout is not None:
                    output = self._run_with_timeout(step, context, default_input, step.timeout)
                else:
                    output = step.execute(self, context, default_input)
                context.step_outputs[step.id] = output
                result = StepResult(
                    step_id=step.id,
                    output=output,
                    attempts=attempts,
                    elapsed_seconds=round(time.monotonic() - started, 4),
                )
                self._step_results[step.id] = result
                self._notify_step(result)
                return output
            except Exception as exc:  # noqa: BLE001
                if attempts <= step.retries:
                    continue
                error = f"step '{step.id}' failed: {type(exc).__name__}: {exc}"
                self._errors.append(error)
                result = StepResult(
                    step_id=step.id,
                    error=error,
                    attempts=attempts,
                    elapsed_seconds=round(time.monotonic() - started, 4),
                )
                self._step_results[step.id] = result
                self._notify_step(result)
                if self.fail_fast:
                    raise WorkflowError(error) from exc
                return ""

    def _notify_step(self, result: StepResult) -> None:
        if self.on_step_complete is not None:
            # step hooks are observability conveniences; never break the run
            with contextlib.suppress(Exception):
                self.on_step_complete(result)
        if self.observer is not None:
            self.observer.event_bus.publish(
                RunEvent(
                    event_type="workflow_step",
                    agent_id=self.name,
                    data={
                        "step_id": result.step_id,
                        "output": result.output,
                        "error": result.error,
                    },
                )
            )

    def _run_with_timeout(
        self, step: Step, context: WorkflowContext, default_input: str, timeout: float
    ) -> str:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(step.execute, self, context, default_input)
            return future.result(timeout=timeout)

    def _run_loop(self, block: LoopBlock, context: WorkflowContext, default_input: str) -> str:
        last_output = default_input
        for _ in range(block.max_iterations):
            last_output = self._run_items(block.steps, context, default_input)
            if block.until is None or block.until(context):
                break
        return last_output

    def _run_parallel(
        self, block: ParallelBlock, context: WorkflowContext, default_input: str
    ) -> str:
        outputs = self._run_parallel_steps(block.steps, context, default_input)
        if block.join is not None:
            joined = str(block.join(outputs, context))
            context.step_outputs["join"] = joined
            return joined
        return "\n".join(outputs)

    def _run_parallel_steps(
        self, steps: list[Step], context: WorkflowContext, default_input: str
    ) -> list[str]:
        with ThreadPoolExecutor(max_workers=len(steps)) as executor:
            futures: list[Future[str]] = [
                executor.submit(self._run_step, step, context, default_input) for step in steps
            ]
            return [future.result() for future in futures]

    # -- async execution -----------------------------------------------------

    async def arun(self, input: str | None = None) -> WorkflowResult:
        """Async variant of `run`; agent steps use `Agent.arun`."""

        async def execute_step(step: Step, ctx: WorkflowContext, default_input: str) -> str:
            step_input = default_input
            if step.input_from is not None:
                step_input = ctx.step_outputs.get(step.input_from, "")
            if step.agent is not None:
                return (await step.agent.arun(step_input)).content
            if step.function is not None:
                result = step.function(step_input, ctx)
                if asyncio.iscoroutine(result):
                    result = await result
                return str(result)
            if step.workflow is not None:
                return (await step.workflow.arun(step_input)).content
            raise ValueError(f"Step '{step.id}' has no agent, function, or workflow")

        async def run_items(
            items: Sequence[WorkflowItem], ctx: WorkflowContext, default_input: str
        ) -> str:
            last_output = default_input
            for item in items:
                if isinstance(item, Step):
                    try:
                        output = await execute_step(item, ctx, default_input)
                        ctx.step_outputs[item.id] = output
                        result = StepResult(step_id=item.id, output=output)
                        self._step_results[item.id] = result
                        self._notify_step(result)
                        last_output = output
                    except Exception as exc:  # noqa: BLE001
                        error = f"step '{item.id}' failed: {type(exc).__name__}: {exc}"
                        self._errors.append(error)
                        result = StepResult(step_id=item.id, error=error)
                        self._step_results[item.id] = result
                        self._notify_step(result)
                        if self.fail_fast:
                            raise WorkflowError(error) from exc
                        last_output = ""
                elif isinstance(item, IfBlock):
                    branch = item.then if item.condition(ctx) else item.otherwise
                    if branch:
                        last_output = await run_items(branch, ctx, default_input)
                elif isinstance(item, LoopBlock):
                    for _ in range(item.max_iterations):
                        last_output = await run_items(item.steps, ctx, default_input)
                        if item.until is None or item.until(ctx):
                            break
                elif isinstance(item, ParallelBlock):
                    outputs = await asyncio.gather(
                        *[execute_step(step, ctx, default_input) for step in item.steps]
                    )
                    for step, output in zip(item.steps, outputs, strict=True):
                        ctx.step_outputs[step.id] = output
                    if item.join is not None:
                        joined = str(item.join(list(outputs), ctx))
                        ctx.step_outputs["join"] = joined
                        last_output = joined
                    else:
                        last_output = "\n".join(outputs)
            return last_output

        context = WorkflowContext(workflow_id=self.name or "workflow")
        self._reset_run_state()
        output = await run_items(self.items, context, input or "")
        self.last_result = WorkflowResult(
            content=output,
            outputs=dict(context.step_outputs),
            step_results=dict(self._step_results),
            errors=list(self._errors),
        )
        return self.last_result
