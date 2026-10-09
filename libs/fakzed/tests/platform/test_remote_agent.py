"""RemoteAgent tests: protocol handling against a stdlib HTTP mock server.

The mock server speaks the fakzed-server contract (JSON chat, SSE stream,
session ids) so the SDK-side client is exercised without importing the
platform package.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fakzed import RemoteAgent, RemoteAgentError, RunResponse
from fakzed.model import Usage


class MockPlatformHandler(BaseHTTPRequestHandler):
    """A minimal fakzed-server contract: chat JSON + SSE stream + resume."""

    script: list = []
    received: list = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length)) if length else {}
        self.received.append(body)
        if not self.headers.get("X-API-Key"):
            self.send_error(401)
            return
        if self.path.endswith("/chat/stream"):
            chunks = [
                {"event": "chunk", "content": "hel"},
                {"event": "chunk", "content": "lo"},
                {
                    "event": "complete",
                    "content": "hello",
                    "session_id": "s-123",
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                },
            ]
            payload = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path.endswith("/resume"):
            response = {
                "event": "complete",
                "content": "resumed",
                "session_id": body.get("session_id") or "s-123",
            }
        else:
            response = {
                "event": "complete",
                "content": self.script.pop(0) if self.script else "ok",
                "session_id": body.get("session_id") or "s-123",
            }
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # silence
        return


@pytest.fixture
def mock_platform() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockPlatformHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_remote_run_and_session_adoption(mock_platform) -> None:
    remote = RemoteAgent(name="greeter", base_url=mock_platform, api_key="k")

    response = remote.run("hi")

    assert isinstance(response, RunResponse)
    assert response.content == "ok"
    assert remote.session_id == "s-123"


def test_remote_run_replays_session_id(mock_platform) -> None:
    remote = RemoteAgent(name="greeter", base_url=mock_platform, api_key="k", session_id="s-42")

    response = remote.run("hi again")

    assert response.content == "ok"
    # the client replayed its session id so the server can recover history
    assert MockPlatformHandler.received[-1]["session_id"] == "s-42"


def test_remote_stream_parses_sse(mock_platform) -> None:
    remote = RemoteAgent(name="greeter", base_url=mock_platform, api_key="k")

    events = list(remote.run_stream("hi"))

    assert [e.event for e in events] == ["chunk", "chunk", "complete"]
    assert events[-1].content == "hello"
    assert events[-1].usage == Usage(input_tokens=3, output_tokens=2)
    assert remote.session_id == "s-123"


def test_remote_resume(mock_platform) -> None:
    remote = RemoteAgent(name="greeter", base_url=mock_platform, api_key="k")

    response = remote.resume()

    assert response.event == "complete"
    assert response.content == "resumed"


def test_remote_missing_api_key_is_rejected(mock_platform) -> None:
    remote = RemoteAgent(name="greeter", base_url=mock_platform)

    with pytest.raises(RemoteAgentError, match="401"):
        remote.run("hi")


def test_remote_unreachable_server_raises() -> None:
    remote = RemoteAgent(name="greeter", base_url="http://127.0.0.1:1", timeout=1.0)

    with pytest.raises(RemoteAgentError, match="unreachable"):
        remote.run("hi")


def test_remote_arun_and_aresume() -> None:
    import asyncio

    async def scenario(base_url: str) -> None:
        remote = RemoteAgent(name="greeter", base_url=base_url, api_key="k")
        response = await remote.arun("hi")
        assert response.content == "ok"
        resumed = await remote.aresume()
        assert resumed.content == "resumed"

    server = ThreadingHTTPServer(("127.0.0.1", 0), MockPlatformHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        asyncio.run(scenario(base))
    finally:
        server.shutdown()
        server.server_close()


def test_remote_arun_stream() -> None:
    import asyncio

    async def scenario(base_url: str) -> None:
        remote = RemoteAgent(name="greeter", base_url=base_url, api_key="k")
        events = [e async for e in remote.arun_stream("hi")]
        assert events[-1].content == "hello"

    server = ThreadingHTTPServer(("127.0.0.1", 0), MockPlatformHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        asyncio.run(scenario(base))
    finally:
        server.shutdown()
        server.server_close()
