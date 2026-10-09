"""Phase 8 tests: observability, evals, background runs, scheduling."""

import time

from conftest import FakeModel

from fakzed import (
    Agent,
    BackgroundRunner,
    EvalCase,
    EventBus,
    MetricsCollector,
    RunEvent,
    RunObserver,
    Scheduler,
    Tracer,
    Workflow,
    eval_agent,
)
from fakzed.model import ModelResponse, ToolCall, Usage
from fakzed.tools import tool
from fakzed.workflow import Step


def make_tool_agent(model: FakeModel) -> Agent:
    @tool
    def lookup(query: str) -> str:
        """Look something up."""
        return f"result for {query}"

    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="lookup", arguments={"query": "x"})],
        ),
        ModelResponse(content="done", usage=Usage(input_tokens=10, output_tokens=5)),
    )
    return Agent(name="observed", model=model, tools=[lookup])


# -- 8.1 event bus ---------------------------------------------------------------


def test_event_bus_publishes_run_and_tool_events() -> None:
    bus = EventBus()
    model = FakeModel()
    agent = make_tool_agent(model)
    agent.observer = RunObserver(event_bus=bus)

    agent.run("hello")

    events = [e.event_type for e in bus.history]
    assert "agent_run_start" in events
    assert "tool_call" in events
    assert "tool_result" in events
    assert "agent_run_end" in events
    # events carry the run id and agent identity
    assert all(e.run_id is not None for e in bus.history)
    assert bus.history[0].agent_id == "observed"


def test_event_bus_subscriber_receives_events() -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe(lambda event: received.append(event.event_type))

    bus.publish(RunEvent(event_type="custom"))

    assert received == ["custom"]


def test_event_bus_drain_clears_history() -> None:
    bus = EventBus()
    bus.publish(RunEvent(event_type="a"))
    bus.publish(RunEvent(event_type="b"))

    drained = bus.drain()

    assert [e.event_type for e in drained] == ["a", "b"]
    assert bus.history == []


# -- 8.2 tracing -----------------------------------------------------------------


def test_tracer_records_spans_with_duration() -> None:
    tracer = Tracer()
    model = FakeModel()
    agent = make_tool_agent(model)
    agent.observer = RunObserver(tracer=tracer, event_bus=EventBus())

    agent.run("hi")

    assert len(tracer.all_traces()) == 1
    trace = tracer.all_traces()[0]
    span = trace.root_span()
    assert span is not None
    assert span.name == "agent.run"
    assert span.attributes["agent"] == "observed"
    assert span.ended_at is not None
    assert span.duration_ms() is not None and span.duration_ms() >= 0


# -- 8.3 metrics -----------------------------------------------------------------


def test_metrics_collector_records_run_totals() -> None:
    collector = MetricsCollector()
    model = FakeModel()
    agent = make_tool_agent(model)
    agent.observer = RunObserver(metrics=collector, event_bus=EventBus())

    agent.run("first")
    # re-script the model for the second run
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="lookup", arguments={"query": "y"})],
        ),
        ModelResponse(content="done", usage=Usage(input_tokens=10, output_tokens=5)),
    )
    agent.run("second")

    assert len(collector.all()) == 2
    summary = collector.summary()
    assert summary.runs == 2
    assert summary.total_input_tokens == 20
    assert summary.total_output_tokens == 10
    assert summary.total_tool_calls == 2
    for metrics in collector.all():
        assert metrics.latency_ms() is not None


# -- 8.4 evals -------------------------------------------------------------------


def test_eval_agent_reports_accuracy() -> None:
    model = FakeModel()
    model.enqueue(
        ModelResponse(content="the capital is Paris"),
        ModelResponse(content="the capital is London"),
        ModelResponse(content="the capital is Tokyo"),
    )
    agent = Agent(name="geography", model=model)

    report = eval_agent(
        agent,
        cases=[
            EvalCase(name="france", input="capital of France?", expected="Paris"),
            EvalCase(name="uk", input="capital of UK?", expected="London"),
            EvalCase(name="japan", input="capital of Japan?", expected="Rome"),
        ],
    )

    assert report.total == 3
    assert report.passed == 2
    assert report.accuracy == 0.6667
    assert [r.case_name for r in report.results] == ["france", "uk", "japan"]


def test_eval_agent_custom_judge() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="roughly equal to 4"))
    agent = Agent(name="math", model=model)

    report = eval_agent(
        agent,
        cases=[EvalCase(name="approx", input="2+2?", expected="4")],
        judge=lambda output, expected: "4" in output,  # exact-match would fail
    )

    assert report.passed == 1


# -- 8.5 background execution ------------------------------------------------------


def test_background_runner_completes_and_polls() -> None:
    model = FakeModel()
    model.enqueue(ModelResponse(content="background answer"))
    agent = Agent(name="bg", model=model)
    runner = BackgroundRunner()

    run_id = runner.submit(lambda: agent.run("long task"))

    finished = runner.wait(run_id, timeout=5.0)
    assert finished.status.value == "completed"
    assert finished.result is not None and finished.result.content == "background answer"
    assert runner.get(run_id) is not None


def test_background_runner_records_failure() -> None:
    runner = BackgroundRunner()

    def explode():
        raise ValueError("boom")

    run_id = runner.submit(explode)
    finished = runner.wait(run_id, timeout=5.0)

    assert finished.status.value == "failed"
    assert "boom" in (finished.error or "")


def test_background_runner_cancel_pending_run() -> None:
    import threading

    runner = BackgroundRunner()
    started = threading.Event()

    def slow():
        started.set()
        time.sleep(5.0)

    run_id = runner.submit(slow)
    assert started.wait(timeout=2.0)
    assert runner.cancel(run_id) is True
    assert runner.get(run_id).status.value == "cancelled"


# -- 8.6 scheduler -----------------------------------------------------------------


def test_scheduler_runs_jobs_on_interval() -> None:
    counts: list[int] = [0]

    def job() -> None:
        counts[0] += 1

    scheduler = Scheduler(tick_seconds=0.02)
    job_id = scheduler.add_job(job, interval_seconds=0.05)
    scheduler.start()
    try:
        time.sleep(0.25)
    finally:
        scheduler.stop()

    assert scheduler.jobs[job_id].run_count >= 3
    assert counts[0] >= 3


def test_scheduler_records_job_errors() -> None:
    def bad_job() -> None:
        raise RuntimeError("job failed")

    scheduler = Scheduler(tick_seconds=0.02)
    job_id = scheduler.add_job(bad_job, interval_seconds=0.05)
    scheduler.start()
    try:
        time.sleep(0.2)
    finally:
        scheduler.stop()

    job = scheduler.jobs[job_id]
    assert job.run_count >= 1
    assert "job failed" in (job.last_error or "")


def test_scheduler_remove_job() -> None:
    scheduler = Scheduler()
    job_id = scheduler.add_job(lambda: None, interval_seconds=1.0)

    assert scheduler.remove_job(job_id) is True
    assert scheduler.remove_job("missing") is False
    assert scheduler.jobs == {}


# -- workflow events ----------------------------------------------------------------


def test_workflow_publishes_step_events() -> None:
    bus = EventBus()

    def upper(input: str, ctx):
        return input.upper()

    workflow = Workflow(
        name="wf",
        items=[Step(id="up", function=upper)],
        observer=RunObserver(event_bus=bus),
    )

    workflow.run("hello")

    step_events = [e for e in bus.history if e.event_type == "workflow_step"]
    assert len(step_events) == 1
    assert step_events[0].data["step_id"] == "up"
    assert step_events[0].data["output"] == "HELLO"
