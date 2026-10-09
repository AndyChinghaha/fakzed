"""Phase 9 demo: platform server + SDK RemoteAgent end-to-end.

Runs a real fakzed-server on a background thread, registers a scripted agent,
then drives it from the SDK via RemoteAgent — chat, session recovery, SSE
streaming, HITL pause/resume, a background run, and monitoring queries.

    cd libs/fakzed
    uv run python ../../scripts/server_demo.py
"""

import threading
import time
from collections.abc import Sequence
from typing import Any

import uvicorn
from pydantic import Field

from fakzed import Agent, InMemoryStorage, RemoteAgent
from fakzed.model import Message, Model, ModelResponse, ToolCall, Usage
from fakzed.tools import tool
from fakzed_server import FakzedServer

ADMIN_KEY = "fz_demo_admin_key"


class ScriptedModel(Model):
    """Minimal model with a scripted queue of responses."""

    id: str = "scripted"
    provider: str = "demo"
    responses: list[ModelResponse] = Field(default_factory=list)
    calls: list[list[Message]] = Field(default_factory=list)

    def _pop(self, messages: Sequence[Message], tools: Sequence | None = None) -> ModelResponse:
        self.calls.append(list(messages))
        return self.responses.pop(0) if self.responses else ModelResponse(content="")

    def response(self, messages, *, tools=None, response_format=None, **kwargs: Any):
        return self._pop(messages, tools)

    def response_stream(self, messages, *, tools=None, response_format=None, **kwargs: Any):
        result = self._pop(messages, tools)
        yield ModelResponse(content=result.content, event="chunk")
        yield result

    async def aresponse(self, messages, *, tools=None, response_format=None, **kwargs: Any):
        return self._pop(messages, tools)

    async def aresponse_stream(self, messages, *, tools=None, response_format=None, **kwargs: Any):
        result = self._pop(messages, tools)
        yield ModelResponse(content=result.content, event="chunk")
        yield result


def main() -> None:
    print("=== 阶段 9 演示：平台层 fakzed-server + SDK RemoteAgent ===\n")

    # 1) build the platform with a scripted agent
    server = FakzedServer(
        admin_api_key=ADMIN_KEY, storage=InMemoryStorage(), db_path="demo_runs.json"
    )

    @tool
    def lookup(query: str) -> str:
        """Look something up."""
        return f"result for {query}"

    scripted = ScriptedModel(
        responses=[
            ModelResponse(content="answer one", usage=Usage(input_tokens=10, output_tokens=5)),
            ModelResponse(content="answer two (history: ping)"),
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="lookup", arguments={"query": "x"})],
            ),
            ModelResponse(content="approved final"),
            ModelResponse(content="streamed words"),
        ]
    )
    agent = Agent(name="demo-agent", model=scripted, tools=[lookup])
    server.register(agent)

    config = uvicorn.Config(server.app, host="127.0.0.1", port=8765, log_level="error")
    uvicorn_server = uvicorn.Server(config)
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 10.0
        while not uvicorn_server.started and time.time() < deadline:
            time.sleep(0.05)

        remote = RemoteAgent(name="demo-agent", base_url="http://127.0.0.1:8765", api_key=ADMIN_KEY)

        # 2) chat + session recovery
        first = remote.run("ping")
        print(f"[chat]    {first.content!r}  session={remote.session_id}")
        second = remote.run("pong")
        print(f"[chat]    {second.content!r}  (session recovered)")

        # 3) HITL pause + resume
        paused = remote.run("do the thing", stop_after_tool_call=True)
        print(
            f"[hitl]    paused on tool {paused.tool_call.name!r} -> result={paused.tool_call_result!r}"
        )
        resumed = remote.resume()
        print(f"[hitl]    resumed -> {resumed.content!r}")

        # 4) SSE streaming
        events = list(remote.run_stream("tell me a story"))
        chunks = "".join(e.content for e in events if e.event == "chunk")
        print(f"[stream]  chunks={chunks!r} final={events[-1].content!r}")

        # 5) background run via the platform API
        run_id = server.runs.submit("demo-agent", "background job").run_id
        finished = server.runs.wait(run_id, timeout=5.0)
        print(f"[runs]    run {run_id} -> {finished.status}")

        # 6) monitoring over the same backends
        summary = server.monitoring.summary()
        print(
            f"[metrics] runs={summary['runs']} in_tokens={summary['total_input_tokens']} "
            f"tool_calls={summary['total_tool_calls']}"
        )
        print(
            f"[events]  {len(server.monitoring.event_bus.history)} events, "
            f"{len(server.monitoring.tracer.all_traces())} traces captured"
        )
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=5.0)
        print("\n=== 演示结束 ===")


if __name__ == "__main__":
    main()
