"""Run management: long-running agent executions behind create/query/cancel.

Reuses the SDK `BackgroundRunner` (thread pool + wait/cancel polling) so the
platform inherits the same semantics as embedded usage. Run records are
persisted via `JsonStore` and restored on restart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from fakzed.runtime import BackgroundRunner


class RunRecord(BaseModel):
    """Persistable snapshot of a background run."""

    run_id: str
    agent: str
    status: str
    input: str | None = None
    output: str | None = None
    error: str | None = None


class RunManager(BaseModel):
    """Submits agent calls to a BackgroundRunner and persists the outcome."""

    runner: BackgroundRunner = Field(default_factory=BackgroundRunner)
    store: Any = Field(default=None, exclude=True)
    agent_factory: Callable[[str], Any] | None = Field(default=None, exclude=True)

    def submit(
        self,
        agent_name: str,
        message: str,
        *,
        session_id: str | None = None,
        stop_after_tool_call: bool = False,
    ) -> RunRecord:
        """Start a background run of a registered agent; returns the record."""
        run_id = self.runner.submit(
            lambda: self._call(agent_name, message, session_id, stop_after_tool_call)
        )
        record = RunRecord(run_id=run_id, agent=agent_name, status="pending", input=message)
        self._persist(record)
        return record

    def _call(
        self,
        agent_name: str,
        message: str,
        session_id: str | None,
        stop_after_tool_call: bool,
    ) -> Any:
        """Resolve the registered instance and run it in the worker thread."""
        if self.agent_factory is None:
            raise RuntimeError("RunManager.agent_factory is not wired")
        instance = self.agent_factory(agent_name)
        if session_id and getattr(instance, "session_id", None) is None:
            instance.session_id = session_id
        return instance.run(message, stop_after_tool_call=stop_after_tool_call)

    def get(self, run_id: str) -> RunRecord | None:
        """Return the current (in-memory) state of a run."""
        run = self.runner.get(run_id)
        record = self._persisted(run_id)
        if run is None:
            return record
        if record is not None:
            record.status = run.status.value
            record.output = self._content_of(run.result)
            record.error = run.error
            self._persist(record)
        return record

    def wait(self, run_id: str, timeout: float = 300.0) -> RunRecord | None:
        run = self.runner.wait(run_id, timeout=timeout)
        if run is None:
            return self._persisted(run_id)
        record = self._persisted(run_id) or RunRecord(run_id=run_id, agent="?", status="running")
        record.status = run.status.value
        record.output = self._content_of(run.result)
        record.error = run.error
        self._persist(record)
        return record

    def cancel(self, run_id: str) -> bool:
        return self.runner.cancel(run_id)

    def list(self) -> list[RunRecord]:
        records = [r for r in self.store.all().values() if isinstance(r, dict)]
        return [RunRecord(**r) for r in records]

    @staticmethod
    def _content_of(result: Any) -> str | None:
        content = getattr(result, "content", None)
        return content if isinstance(content, str) else str(content) if content else None

    def _persisted(self, run_id: str) -> RunRecord | None:
        raw = self.store.get(run_id) if self.store is not None else None
        return RunRecord(**raw) if isinstance(raw, dict) else None

    def _persist(self, record: RunRecord) -> None:
        if self.store is not None:
            self.store.put(record.run_id, record.model_dump())
