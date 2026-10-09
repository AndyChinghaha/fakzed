"""Background execution: run long tasks off-thread and poll their status."""

import threading
import time
import uuid
from collections.abc import Callable
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from fakzed.agent.agent import RunResponse


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundRun(BaseModel):
    """State of one background run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    status: RunStatus = RunStatus.PENDING
    result: RunResponse | None = None
    error: str | None = None
    created_at: float = Field(default_factory=time.time)
    started_at: float | None = None
    ended_at: float | None = None


class BackgroundRunner(BaseModel):
    """Executes callables on worker threads and tracks their status."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    runs: dict[str, BackgroundRun] = Field(default_factory=dict, exclude=True)
    max_workers: int = 4

    def submit(self, fn: Callable[[], RunResponse], run_id: str | None = None) -> str:
        """Start `fn` in the background; returns the run id for polling."""
        run_id = run_id or uuid.uuid4().hex[:12]
        run = BackgroundRun(run_id=run_id, status=RunStatus.PENDING)
        self.runs[run_id] = run

        def worker() -> None:
            run.status = RunStatus.RUNNING
            run.started_at = time.time()
            try:
                run.result = fn()
                run.status = RunStatus.COMPLETED
            except Exception as exc:  # noqa: BLE001
                run.error = f"{type(exc).__name__}: {exc}"
                run.status = RunStatus.FAILED
            finally:
                run.ended_at = time.time()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return run_id

    def get(self, run_id: str) -> BackgroundRun | None:
        return self.runs.get(run_id)

    def list_runs(self) -> list[BackgroundRun]:
        return list(self.runs.values())

    def cancel(self, run_id: str) -> bool:
        """Mark a pending/running run as cancelled (threads are not killed)."""
        run = self.runs.get(run_id)
        if run is None or run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
            return False
        run.status = RunStatus.CANCELLED
        run.ended_at = time.time()
        return True

    def wait(self, run_id: str, timeout: float | None = None) -> BackgroundRun:
        """Block until the run reaches a terminal state."""
        deadline = None if timeout is None else time.time() + timeout
        while True:
            run = self.runs.get(run_id)
            if run is None or run.status in (
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            ):
                return run  # type: ignore[return-value]
            if deadline is not None and time.time() >= deadline:
                return run
            time.sleep(0.01)
