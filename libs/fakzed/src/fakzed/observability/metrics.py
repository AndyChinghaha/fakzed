"""Run metrics: token usage, latency, tool-call counts, aggregates."""

import time
import uuid

from pydantic import BaseModel, ConfigDict, Field

from fakzed.model.response import Usage
from fakzed.observability.events import DEFAULT_EVENT_BUS, EventBus
from fakzed.observability.trace import NOOP_TRACER, Tracer


class RunMetrics(BaseModel):
    """Per-run metrics collected from model usage and run timing."""

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str | None = None
    started_at: float = Field(default_factory=time.time)
    ended_at: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: int = 0
    iterations: int = 0

    def latency_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return round((self.ended_at - self.started_at) * 1000, 3)

    def absorb_usage(self, usage: Usage | None) -> None:
        if usage is None:
            return
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.total_tokens += usage.total_tokens or 0


class AggregateMetrics(BaseModel):
    """Aggregated totals over a set of runs."""

    runs: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tool_calls: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0


class MetricsCollector(BaseModel):
    """Collects per-run metrics and answers aggregate queries."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    metrics: list[RunMetrics] = Field(default_factory=list, exclude=True)
    max_metrics: int = 10000

    def record(self, metrics: RunMetrics) -> None:
        self.metrics.append(metrics)
        if len(self.metrics) > self.max_metrics:
            self.metrics = self.metrics[-self.max_metrics :]

    def get(self, run_id: str) -> RunMetrics | None:
        for metrics in reversed(self.metrics):
            if metrics.run_id == run_id:
                return metrics
        return None

    def all(self) -> list[RunMetrics]:
        return list(self.metrics)

    def summary(self) -> AggregateMetrics:
        latencies = [m.latency_ms() for m in self.metrics]
        finished = [latency for latency in latencies if latency is not None]
        return AggregateMetrics(
            runs=len(self.metrics),
            total_input_tokens=sum(m.input_tokens for m in self.metrics),
            total_output_tokens=sum(m.output_tokens for m in self.metrics),
            total_tool_calls=sum(m.tool_calls for m in self.metrics),
            total_cost_usd=round(sum(m.cost_usd for m in self.metrics), 6),
            avg_latency_ms=round(sum(finished) / len(finished), 3) if finished else 0.0,
        )

    def export_json(self) -> str:
        import json

        return json.dumps([m.model_dump() for m in self.metrics], ensure_ascii=False, default=str)


class RunObserver(BaseModel):
    """Bundle of observability backends attachable to an Agent or Workflow.

    `event_bus` defaults to the global bus; `tracer` defaults to a no-op
    collector; `metrics` is None (not collected) unless provided.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    event_bus: EventBus = Field(default_factory=lambda: DEFAULT_EVENT_BUS)
    tracer: Tracer = Field(default_factory=lambda: NOOP_TRACER)
    metrics: MetricsCollector | None = None
