"""RemoteAgent: run an agent deployed on a fakzed-server over HTTP.

A `RemoteAgent` mirrors the local `Agent` interface (`run`/`arun`/`run_stream`/
`arun_stream`/`resume`) but executes remotely. It uses only the standard
library (`urllib`), so the SDK stays dependency-light. Sessions are
recoverable: the server stores session history, and `session_id` is captured
from the first response and replayed on subsequent calls.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator, Iterator
from typing import Any

from pydantic import BaseModel

from fakzed.agent import RunResponse


class RemoteAgentError(Exception):
    """Raised when the remote platform call fails."""


class RemoteAgent(BaseModel):
    """Handle to a remotely deployed agent, addressed by registry name."""

    name: str
    base_url: str = "http://127.0.0.1:8000"
    api_key: str | None = None
    session_id: str | None = None
    timeout: float = 300.0

    # -- public interface (mirrors Agent) ------------------------------------

    def run(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        stop_after_tool_call: bool = False,
    ) -> RunResponse:
        """Run the remote agent and return its final (or paused) response."""
        payload: dict[str, Any] = {"message": message, "stop_after_tool_call": stop_after_tool_call}
        if self.session_id is not None:
            payload["session_id"] = self.session_id
        if context is not None:
            payload["context"] = context
        data = self._request("POST", f"/api/agents/{self._quote()}/chat", payload)
        return self._adopt(data)

    async def arun(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        stop_after_tool_call: bool = False,
    ) -> RunResponse:
        import asyncio

        return await asyncio.to_thread(
            self.run, message, context=context, stop_after_tool_call=stop_after_tool_call
        )

    def run_stream(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> Iterator[RunResponse]:
        """Streamed variant: yields chunk events and a final complete event."""
        payload: dict[str, Any] = {"message": message}
        if self.session_id is not None:
            payload["session_id"] = self.session_id
        if context is not None:
            payload["context"] = context
        for data in self._stream_request(f"/api/agents/{self._quote()}/chat/stream", payload):
            yield self._adopt(data)

    async def arun_stream(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[RunResponse]:
        import asyncio

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[RunResponse | None] = asyncio.Queue()

        def produce() -> None:
            for event in self.run_stream(message, context=context):
                loop.call_soon_threadsafe(queue.put_nowait, event)
            loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, produce)
        while True:
            event = await queue.get()
            if event is None:
                return
            yield event

    def resume(self) -> RunResponse:
        """Continue a remote run paused with `stop_after_tool_call=True`."""
        data = self._request("POST", f"/api/agents/{self._quote()}/resume", {})
        return self._adopt(data)

    async def aresume(self) -> RunResponse:
        import asyncio

        return await asyncio.to_thread(self.resume)

    # -- internals -------------------------------------------------------------

    def _quote(self) -> str:
        return urllib.parse.quote(self.name, safe="")

    def _adopt(self, data: dict[str, Any]) -> RunResponse:
        """Build a RunResponse and remember the session id for recovery."""
        session_id = data.get("session_id")
        if session_id:
            self.session_id = session_id
        return RunResponse.model_validate(data)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + path
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, method=method, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace") if exc.fp else str(exc)
            raise RemoteAgentError(f"{method} {path} -> {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RemoteAgentError(f"{method} {path} unreachable: {exc}") from exc

    def _stream_request(self, path: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Parse an SSE response (`data: {...}` lines) into JSON payloads."""
        url = self.base_url.rstrip("/") + path
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers=self._headers())
        try:
            response = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace") if exc.fp else str(exc)
            raise RemoteAgentError(f"POST {path} -> {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RemoteAgentError(f"POST {path} unreachable: {exc}") from exc
        with response:
            for line in response:
                text = line.decode().strip()
                if text.startswith("data:"):
                    yield json.loads(text[len("data:") :].strip())
