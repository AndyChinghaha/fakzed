"""Unified run-event system: every component reports to one event bus."""

import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunEvent(BaseModel):
    """One event emitted during a run.

    Common event types: agent_run_start, agent_run_end, tool_call,
    tool_result, workflow_step, run_error, run_paused.
    """

    event_type: str
    timestamp: float = Field(default_factory=time.time)
    agent_id: str | None = None
    run_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class EventBus(BaseModel):
    """Publish-subscribe bus; keeps a bounded history for later queries."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    subscribers: list[Callable[[RunEvent], None]] = Field(default_factory=list, exclude=True)
    history: list[RunEvent] = Field(default_factory=list, exclude=True)
    max_history: int = 10000

    def publish(self, event: RunEvent) -> None:
        """Fan the event out to subscribers and record it in history."""
        self.history.append(event)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]
        for subscriber in list(self.subscribers):
            try:
                subscriber(event)
            except Exception:  # noqa: BLE001
                # subscriber errors must never break the run
                continue

    def subscribe(self, callback: Callable[[RunEvent], None]) -> None:
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[RunEvent], None]) -> None:
        self.subscribers.remove(callback)

    def drain(self) -> list[RunEvent]:
        """Return and clear the recorded history (for exporters)."""
        events = list(self.history)
        self.history.clear()
        return events


#: Global bus used when an Agent has no bus of its own.
DEFAULT_EVENT_BUS = EventBus()
