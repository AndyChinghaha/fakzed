"""Lightweight tracing: spans per run, queryable after the fact."""

import time
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TraceSpan(BaseModel):
    """One span inside a trace."""

    trace_id: str
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_id: str | None = None
    name: str
    started_at: float = Field(default_factory=time.time)
    ended_at: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return round((self.ended_at - self.started_at) * 1000, 3)


class Trace(BaseModel):
    """A full trace: root span plus its children."""

    trace_id: str
    spans: list[TraceSpan] = Field(default_factory=list)

    def root_span(self) -> TraceSpan | None:
        return self.spans[0] if self.spans else None


class Tracer(BaseModel):
    """Tracing backend. The in-memory implementation keeps every trace."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    traces: dict[str, Trace] = Field(default_factory=dict, exclude=True)
    max_traces: int = 1000

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> TraceSpan:
        trace_id = uuid.uuid4().hex[:16]
        span = TraceSpan(trace_id=trace_id, name=name, attributes=attributes or {})
        self.traces[trace_id] = Trace(trace_id=trace_id, spans=[span])
        if len(self.traces) > self.max_traces:
            oldest = next(iter(self.traces))
            del self.traces[oldest]
        return span

    def end_span(self, span: TraceSpan) -> None:
        span.ended_at = time.time()

    def get_trace(self, trace_id: str) -> Trace | None:
        return self.traces.get(trace_id)

    def all_traces(self) -> list[Trace]:
        return list(self.traces.values())


#: Zero-cost default when no tracer is configured.
NOOP_TRACER = Tracer()
