"""Tracing & monitoring: expose SDK observability backends over the API.

The platform taps the same `EventBus`/`Tracer`/`MetricsCollector` the SDK
uses, so one `RunObserver` shared with the served agents gives the server
visibility into every run without a second instrumentation pass.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fakzed.observability import (
    EventBus,
    MetricsCollector,
    RunEvent,
    RunObserver,
    Trace,
    Tracer,
)


class MonitoringStore(BaseModel):
    """Aggregates platform-wide observability state and query helpers."""

    model_config = {"arbitrary_types_allowed": True}

    event_bus: EventBus = Field(default_factory=EventBus)
    tracer: Tracer = Field(default_factory=Tracer)
    metrics: MetricsCollector = Field(default_factory=MetricsCollector)

    def observer(self) -> RunObserver:
        """A RunObserver wired to this store, attachable to served agents."""
        return RunObserver(event_bus=self.event_bus, tracer=self.tracer, metrics=self.metrics)

    def recent_events(self, limit: int = 200) -> list[RunEvent]:
        return list(self.event_bus.history[-limit:])

    def traces(self, limit: int = 20) -> list[Trace]:
        return self.tracer.all_traces()[-limit:]

    def summary(self) -> dict:
        return self.metrics.summary().model_dump()

    def cost_by_agent(self) -> dict[str, float]:
        costs: dict[str, float] = {}
        for run in self.metrics.all():
            if run.agent_name:
                costs[run.agent_name] = costs.get(run.agent_name, 0.0) + run.cost_usd
        return costs
