"""Platform-level persistence: run records and API keys survive restarts.

A small JSON-file backend with a threading lock keeps the platform layer
dependency-free while still restoring runs (status/results) and sessions
across process restarts. Sessions themselves live in the SDK `Storage`
backend the served agents are configured with.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, PrivateAttr


class JsonStore(BaseModel):
    """Append-friendly JSON persistence: a dict namespace on disk."""

    path: Path
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _data: dict[str, Any] = PrivateAttr(default_factory=dict)

    def model_post_init(self, _: Any) -> None:
        if self.path.exists():
            try:
                with self.path.open(encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._flush()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            value = self._data.pop(key, default)
            self._flush()
            return value

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def _flush(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, default=str)
        tmp.replace(self.path)
