"""Phase 9 tests: registry, REST/SSE chat, auth, tenancy, runs, monitoring."""

import json
import threading
import time

import uvicorn
from conftest import ADMIN_KEY, FakeModel, auth_headers, register_echo_agent
from fastapi.testclient import TestClient

from fakzed import Agent, RemoteAgent
from fakzed.model import ModelResponse, ToolCall, Usage
from fakzed.tools import tool
from fakzed_server import FakzedServer


def parse_sse(content: str) -> list[dict]:
    """Parse an SSE response body into JSON payloads."""
    payloads = []
    for line in content.splitlines():
        if line.startswith("data:"):
            payloads.append(json.loads(line[len("data:") :].strip()))
    return payloads


# -- 9.1 registry -----------------------------------------------------------------


def test_registry_lists_registered_agents(platform) -> None:
    client, server = platform
    register_echo_agent(server)

    response = client.get("/api/agents", headers=auth_headers())

    assert response.status_code == 200
    agents = response.json()
    assert [a["name"] for a in agents] == ["echo"]
    assert agents[0]["kind"] == "Agent"
    assert agents[0]["enabled"] is True


def test_registry_unknown_agent_404(platform) -> None:
    client, _ = platform
    response = client.post(
        "/api/agents/missing/chat", json={"message": "hi"}, headers=auth_headers()
    )
    assert response.status_code == 404


def test_registry_create_agent_via_api(platform) -> None:
    client, server = platform

    # unknown provider is rejected cleanly
    bad = client.post(
        "/api/agents",
        json={"name": "x", "model": "nope:nothing"},
        headers=auth_headers(),
    )
    assert bad.status_code == 400

    # a known provider registers and appears in the listing
    created = client.post(
        "/api/agents",
        json={
            "name": "api-created",
            "model": "deepseek:deepseek-chat",
            "description": "made via REST",
            "instructions": "be brief",
        },
        headers=auth_headers(),
    )
    assert created.status_code == 200
    assert created.json()["kind"] == "Agent"
    entry = server.registry.get("api-created")
    assert entry.instance.instructions == "be brief"

    duplicate = client.post(
        "/api/agents",
        json={"name": "api-created", "model": "deepseek:deepseek-chat"},
        headers=auth_headers(),
    )
    assert duplicate.status_code == 409


def test_registry_disable_agent_forbids_chat(platform) -> None:
    client, server = platform
    register_echo_agent(server)

    patched = client.patch("/api/agents/echo", json={"enabled": False}, headers=auth_headers())
    assert patched.status_code == 200
    chat = client.post("/api/agents/echo/chat", json={"message": "hi"}, headers=auth_headers())
    assert chat.status_code == 403


# -- 9.2 chat & SSE ------------------------------------------------------------------


def test_chat_returns_content_and_session_id(platform) -> None:
    client, server = platform
    model = register_echo_agent(server)
    model.enqueue(ModelResponse(content="hello from server"))

    response = client.post("/api/agents/echo/chat", json={"message": "hi"}, headers=auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "hello from server"
    assert data["event"] == "complete"
    assert data["session_id"]  # server assigned a session id


def test_chat_streams_sse_events(platform) -> None:
    client, server = platform
    model = register_echo_agent(server)
    model.enqueue(ModelResponse(content="streamed"))

    response = client.post(
        "/api/agents/echo/chat/stream", json={"message": "hi"}, headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert events[0]["event"] == "chunk"
    assert events[-1]["event"] == "complete"
    assert events[-1]["content"] == "streamed"


def test_chat_session_recovery_replays_history(platform) -> None:
    client, server = platform
    model = register_echo_agent(server)
    model.enqueue(ModelResponse(content="first answer"))
    first = client.post(
        "/api/agents/echo/chat", json={"message": "what is 1+1?"}, headers=auth_headers()
    )
    session_id = first.json()["session_id"]

    model.enqueue(ModelResponse(content="second answer"))
    second = client.post(
        "/api/agents/echo/chat",
        json={"message": "thanks", "session_id": session_id},
        headers=auth_headers(),
    )

    assert second.json()["session_id"] == session_id
    # the second call's context contained the first exchange
    history = model.calls[-1]["messages"]
    contents = [m.content for m in history]
    assert "what is 1+1?" in contents
    assert "first answer" in contents

    # the platform can read the session back directly
    fetched = client.get(f"/api/sessions/{session_id}", headers=auth_headers())
    assert fetched.status_code == 200
    assert len(fetched.json()["messages"]) == 4


def test_chat_hitl_pause_and_resume(platform) -> None:
    client, server = platform
    model = FakeModel()

    @tool
    def lookup(query: str) -> str:
        """Look something up."""
        return f"result for {query}"

    agent = Agent(name="hitl", model=model, tools=[lookup])
    server.register(agent)
    model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="lookup", arguments={"query": "x"})],
        ),
        ModelResponse(content="final after approval"),
    )

    paused = client.post(
        "/api/agents/hitl/chat",
        json={"message": "do the thing", "stop_after_tool_call": True},
        headers=auth_headers(),
    )
    assert paused.json()["event"] == "paused"
    assert paused.json()["tool_call"]["name"] == "lookup"

    resumed = client.post("/api/agents/hitl/resume", headers=auth_headers())
    assert resumed.json()["event"] == "complete"
    assert resumed.json()["content"] == "final after approval"


# -- 9.3 auth ------------------------------------------------------------------------


def test_auth_rejects_missing_or_bad_keys(platform) -> None:
    client, _ = platform
    assert client.get("/api/agents").status_code == 401
    assert client.get("/api/agents", headers={"X-API-Key": "wrong"}).status_code == 401


def test_auth_admin_only_endpoints(platform) -> None:
    client, server = platform
    user = server.tenants.create_user("alice")
    raw_user_key, _ = server.auth.issue(name="alice-key", user_id=user.user_id, role="user")

    assert (
        client.patch("/api/agents/x", json={}, headers={"X-API-Key": raw_user_key}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/keys", json={"name": "k"}, headers={"X-API-Key": raw_user_key}
        ).status_code
        == 403
    )


def test_auth_issue_and_revoke_keys(platform) -> None:
    client, _ = platform

    issued = client.post("/api/keys", json={"name": "ops"}, headers=auth_headers())
    assert issued.status_code == 200
    raw = issued.json()["api_key"]
    key_id = issued.json()["key_id"]
    assert raw.startswith("fz_")

    # the issued key works for normal endpoints
    assert client.get("/api/agents", headers={"X-API-Key": raw}).status_code == 200

    revoked = client.delete(f"/api/keys/{key_id}", headers=auth_headers())
    assert revoked.json()["revoked"] is True
    assert client.get("/api/agents", headers={"X-API-Key": raw}).status_code == 401


def test_auth_disabled_server(tmp_path) -> None:
    open_server = FakzedServer(auth_enabled=False, db_path=tmp_path / "open.json")
    open_client = TestClient(open_server.app)
    assert open_client.get("/api/agents").status_code == 200


# -- 9.4 persistence -------------------------------------------------------------------


def test_run_records_survive_restart(tmp_path) -> None:
    db = tmp_path / "runs.json"
    server = FakzedServer(admin_api_key=ADMIN_KEY, db_path=db)
    register_echo_agent(server).enqueue(ModelResponse(content="persisted answer"))
    client = TestClient(server.app)
    created = client.post(
        "/api/runs", json={"agent": "echo", "message": "run me"}, headers=auth_headers()
    )
    run_id = created.json()["run_id"]
    server.runs.wait(run_id, timeout=5.0)

    # simulate a restart: new server, same db file
    server2 = FakzedServer(admin_api_key=ADMIN_KEY, db_path=db)
    record = server2.runs.get(run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.output == "persisted answer"


# -- 9.5 run management -------------------------------------------------------------------


def test_background_run_lifecycle(platform) -> None:
    client, server = platform
    register_echo_agent(server).enqueue(ModelResponse(content="bg answer"))

    created = client.post(
        "/api/runs", json={"agent": "echo", "message": "do it"}, headers=auth_headers()
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    finished = server.runs.wait(run_id, timeout=5.0)
    assert finished.status == "completed"

    fetched = client.get(f"/api/runs/{run_id}", headers=auth_headers())
    assert fetched.json()["output"] == "bg answer"
    listed = client.get("/api/runs", headers=auth_headers())
    assert any(r["run_id"] == run_id for r in listed.json())


def test_background_run_cancel(platform) -> None:
    client, server = platform
    started = threading.Event()

    def slow() -> str:
        started.set()
        time.sleep(5.0)
        return "never"

    run_id = server.runs.runner.submit(slow)
    assert started.wait(timeout=2.0)

    response = client.post(f"/api/runs/{run_id}/cancel", headers=auth_headers())
    assert response.json()["cancelled"] is True
    assert server.runs.runner.get(run_id).status.value == "cancelled"


# -- 9.6 monitoring ------------------------------------------------------------------------


def test_monitoring_endpoints_report_runs(platform) -> None:
    client, server = platform
    model = register_echo_agent(server)
    model.enqueue(ModelResponse(content="ok", usage=Usage(input_tokens=10, output_tokens=5)))
    client.post("/api/agents/echo/chat", json={"message": "hi"}, headers=auth_headers())

    events = client.get("/api/events", headers=auth_headers())
    assert events.status_code == 200
    event_types = [e["event_type"] for e in events.json()]
    assert "agent_run_start" in event_types
    assert "agent_run_end" in event_types

    traces = client.get("/api/traces", headers=auth_headers())
    assert traces.status_code == 200
    assert len(traces.json()) == 1

    summary = client.get("/api/metrics/summary", headers=auth_headers())
    assert summary.status_code == 200
    assert summary.json()["runs"] == 1
    assert summary.json()["total_input_tokens"] == 10


# -- 9.7 tenancy ------------------------------------------------------------------------------


def test_tenancy_user_org_project_flow(platform) -> None:
    client, server = platform

    user = client.post("/api/tenants/users", json={"name": "carol"}, headers=auth_headers())
    assert user.status_code == 200

    org = client.post("/api/tenants/orgs", json={"name": "acme"}, headers=auth_headers())
    assert org.status_code == 200
    org_id = org.json()["org_id"]

    project = client.post(
        "/api/tenants/projects",
        json={"name": "support-bot", "org_id": org_id},
        headers=auth_headers(),
    )
    assert project.status_code == 200
    project_id = project.json()["project_id"]

    listed = client.get(f"/api/tenants/orgs/{org_id}/projects", headers=auth_headers())
    assert [p["name"] for p in listed.json()] == ["support-bot"]

    # agents can be registered under a project scope
    model = FakeModel()
    agent = Agent(name="scoped", model=model)
    server.register(agent, project_id=project_id)
    scoped = client.get("/api/agents", headers=auth_headers())
    by_name = {a["name"]: a for a in scoped.json()}
    assert by_name["scoped"]["project_id"] == project_id


# -- cross-cutting: SDK RemoteAgent against the server -------------------------------------


def test_remote_agent_runs_against_server(platform) -> None:
    _, server = platform
    model = register_echo_agent(server)
    model.enqueue(ModelResponse(content="remote hello"), ModelResponse(content="remote again"))

    config = uvicorn.Config(server.app, host="127.0.0.1", port=0, log_level="error")
    uvicorn_server = uvicorn.Server(config)
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 10.0
        while not uvicorn_server.started and time.time() < deadline:
            time.sleep(0.05)
        assert uvicorn_server.started
        port = uvicorn_server.servers[0].sockets[0].getsockname()[1]

        remote = RemoteAgent(name="echo", base_url=f"http://127.0.0.1:{port}", api_key=ADMIN_KEY)
        first = remote.run("ping")
        assert first.content == "remote hello"
        assert remote.session_id

        second = remote.run("pong")
        assert second.content == "remote again"
        # session recovered: the second server-side call saw the first exchange
        history = model.calls[-1]["messages"]
        assert any(m.content == "ping" for m in history)

        # streamed variant works over the same wire
        model.enqueue(ModelResponse(content="remote stream"))
        events = list(remote.run_stream("ping again"))
        assert events[0].event == "chunk"
        assert events[-1].event == "complete"
        assert events[-1].content == "remote stream"
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=5.0)
