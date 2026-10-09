"""Cookbook 08: platform — fakzed-server + RemoteAgent end-to-end.

Spins up a real fakzed-server on a background thread (random port), registers
an agent, then drives it from the SDK through RemoteAgent: chat, streaming,
session recovery, and HITL.

Run:  python cookbook/08_platform.py
Requires the workspace dev environment (fakzed-server installed).
"""

import threading
import time

import uvicorn
from _cookbook_utils import ScriptedModel

from fakzed import Agent, InMemoryStorage, RemoteAgent, tool
from fakzed.model import ModelResponse, ToolCall
from fakzed_server import FakzedServer

ADMIN_KEY = "cookbook-admin-key"


@tool
def lookup(query: str) -> str:
    """Look something up."""
    return f"lookup result: {query}"


def main() -> None:
    # 1) build the platform with a scripted agent (no real model needed)
    scripted = ScriptedModel(
        responses=[
            ModelResponse(content="你好，我是平台上的 agent。"),
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="lookup", arguments={"query": "天气"})],
            ),
            ModelResponse(content="查询完成：今天晴。"),
            ModelResponse(content="流式片段。"),
        ]
    )
    server = FakzedServer(
        admin_api_key=ADMIN_KEY,
        storage=InMemoryStorage(),
        db_path="cookbook_runs.json",
    )
    server.registry.register(Agent(name="demo", model=scripted, tools=[lookup]))

    # 2) run the real server on a background thread (port 0 = random)
    config = uvicorn.Config(server.app, host="127.0.0.1", port=0, log_level="warning")
    httpd = uvicorn.Server(config)
    thread = threading.Thread(target=httpd.run, daemon=True)
    thread.start()
    for _ in range(100):
        if httpd.started:
            break
        time.sleep(0.05)
    port = httpd.servers[0].sockets[0].getsockname()[1] if httpd.servers else 8000
    base = f"http://127.0.0.1:{port}"
    print(f"fakzed-server 已启动: {base}")

    # 3) SDK RemoteAgent — same interface as a local Agent
    remote = RemoteAgent(name="demo", base_url=base, api_key=ADMIN_KEY)

    resp = remote.run("你好")
    print("1) chat    :", resp.content, "| session:", remote.session_id)

    resp2 = remote.run("查一下天气")
    print("2) tools   :", resp2.content)

    print("3) stream  :", end=" ")
    for chunk in remote.run_stream("再来一次"):
        print(chunk.content, end="")
    print()

    # session recovery: RemoteAgent captures session_id automatically
    resumed = RemoteAgent(
        name="demo", base_url=base, api_key=ADMIN_KEY, session_id=remote.session_id
    )
    resp3 = resumed.run("继续")
    print("4) resume  :", resp3.content or "(队列已空，会话已恢复)")

    httpd.should_exit = True
    print("平台演示完成。")


if __name__ == "__main__":
    main()
