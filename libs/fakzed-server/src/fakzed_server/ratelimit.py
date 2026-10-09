"""In-memory sliding-window rate limiting for the platform API.

Limit buckets are keyed by the hashed API key (authenticated) or client IP
(no-auth mode), so the limiter never keeps raw credentials in memory.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from pydantic import BaseModel, PrivateAttr
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from fakzed_server.auth import hash_key

#: Endpoints exempt from rate limiting (health checks, admin bootstrap).
_DEFAULT_EXCLUDE = frozenset({"/healthz"})


class RateLimiter(BaseModel):
    """Sliding-window limiter: at most `requests_per_minute` hits per key."""

    requests_per_minute: int = 300
    _hits: dict[str, deque[float]] = PrivateAttr(default_factory=dict)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def allow(self, key: str, now: float | None = None) -> bool:
        """Return True when the request is within the limit; False otherwise."""
        now = time.monotonic() if now is None else now
        window = now - 60.0
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= window:
                hits.popleft()
            if len(hits) >= self.requests_per_minute:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """HTTP middleware returning 429 when a caller exceeds the limit."""

    def __init__(
        self,
        app: Any,
        limiter: RateLimiter,
        *,
        exclude: frozenset[str] = _DEFAULT_EXCLUDE,
    ) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.exclude = exclude

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.url.path in self.exclude:
            return await call_next(request)
        raw_key = request.headers.get("X-API-Key")
        if raw_key:
            bucket = "key:" + hash_key(raw_key)
        else:
            host = request.client.host if request.client else "unknown"
            bucket = f"ip:{host}"
        if not self.limiter.allow(bucket):
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded; retry later"},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
