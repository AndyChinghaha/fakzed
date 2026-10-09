"""Scheduler: run jobs on a repeating interval in a background thread."""

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class ScheduledJob(BaseModel):
    """One repeating job."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    job_id: str
    fn: Callable[[], Any]
    interval_seconds: float
    last_run_at: float | None = None
    next_run_at: float | None = None
    run_count: int = 0
    last_error: str | None = None


class Scheduler(BaseModel):
    """Interval scheduler backed by a daemon thread.

    Jobs run sequentially in the tick thread; a misbehaving job delays the
    next tick, so keep job bodies short.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    jobs: dict[str, ScheduledJob] = Field(default_factory=dict, exclude=True)
    tick_seconds: float = 0.1
    _stop_event: threading.Event = PrivateAttr(default_factory=threading.Event)
    _thread: threading.Thread | None = PrivateAttr(default=None)

    def add_job(
        self, fn: Callable[[], Any], interval_seconds: float, job_id: str | None = None
    ) -> str:
        job_id = job_id or uuid.uuid4().hex[:12]
        job = ScheduledJob(job_id=job_id, fn=fn, interval_seconds=interval_seconds)
        job.next_run_at = time.time() + interval_seconds
        self.jobs[job_id] = job
        return job_id

    def remove_job(self, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None

    def start(self) -> None:
        """Start the tick thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the tick thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            for job in list(self.jobs.values()):
                if job.next_run_at is not None and now >= job.next_run_at:
                    try:
                        job.fn()
                        job.last_error = None
                    except Exception as exc:  # noqa: BLE001
                        job.last_error = f"{type(exc).__name__}: {exc}"
                    job.last_run_at = now
                    job.run_count += 1
                    job.next_run_at = now + job.interval_seconds
            self._stop_event.wait(self.tick_seconds)
