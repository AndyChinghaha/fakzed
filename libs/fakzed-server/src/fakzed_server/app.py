"""The platform server: FastAPI app serving the shared agent registry.

Endpoints:
  - chat (REST + SSE streaming) against registered SDK objects
  - HITL resume for paused runs
  - background run management (create/query/cancel)
  - monitoring (events/traces/metrics)
  - tenancy (users/orgs/projects) and API-key issuance

Auth: `X-API-Key` header; admin endpoints require an admin-role key.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fakzed import Agent
from fakzed.storage import Storage
from fakzed_server.auth import ApiKeyStore, Principal
from fakzed_server.monitoring import MonitoringStore
from fakzed_server.persistence import JsonStore
from fakzed_server.ratelimit import RateLimiter, RateLimitMiddleware
from fakzed_server.registry import AgentRegistry, Registered
from fakzed_server.runs import RunManager
from fakzed_server.tenancy import TenantStore


class ChatRequest(BaseModel):
    """Body of a chat call: the message plus optional session context."""

    message: str
    session_id: str | None = None
    context: dict[str, Any] | None = None
    stop_after_tool_call: bool = False


class RunRequest(BaseModel):
    """Body of a background-run submission."""

    agent: str
    message: str
    session_id: str | None = None


class AgentPatch(BaseModel):
    """Body of an agent-management update."""

    enabled: bool | None = None


class AgentCreate(BaseModel):
    """Body of a platform-managed agent creation."""

    name: str
    model: str
    description: str | None = None
    instructions: str | None = None
    project_id: str = "default"
    api_key: str | None = None
    base_url: str | None = None


class TenantRequest(BaseModel):
    """Body of a tenant create call."""

    name: str
    email: str | None = None
    org_id: str | None = None


class KeyRequest(BaseModel):
    """Body of an API-key issuance call."""

    name: str
    user_id: str | None = None
    role: str = "user"


class FakzedServer:
    """Wires registry/tenancy/auth/monitoring/persistence into a FastAPI app."""

    def __init__(
        self,
        *,
        title: str = "Fakzed Platform",
        db_path: str | Path | None = None,
        auth_enabled: bool = True,
        admin_api_key: str | None = None,
        storage: Storage | None = None,
        cors_origins: list[str] | None = None,
        rate_limit_per_minute: int | None = 300,
    ) -> None:
        self.registry = AgentRegistry()
        self.tenants = TenantStore()
        self.auth = ApiKeyStore()
        self.monitoring = MonitoringStore()
        self.persistence = JsonStore(path=Path(db_path) if db_path else Path("fakzed_server.json"))
        self.runs = RunManager(store=self.persistence)
        self.runs.agent_factory = lambda name: self.registry.get(name).instance
        self.auth_enabled = auth_enabled
        self.storage = storage

        if auth_enabled and admin_api_key:
            self._seed_key(admin_api_key, "bootstrap-admin", "admin")

        self.app = FastAPI(title=title)
        # Rate limiting first: it should run before any route logic.
        if rate_limit_per_minute is not None:
            self.app.add_middleware(
                RateLimitMiddleware, limiter=RateLimiter(requests_per_minute=rate_limit_per_minute)
            )
        self.app.add_middleware(
            CORSMiddleware,
            # "*" keeps the dev web UI working out of the box; production
            # deployments should pass explicit `cors_origins` instead.
            allow_origins=cors_origins or ["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self._register_routes()

    # -- setup helpers --------------------------------------------------------

    def _seed_key(self, raw: str, name: str, user_id: str) -> None:
        """Seed the caller-provided bootstrap key with admin role (hash only)."""
        from fakzed_server.auth import ApiKey, hash_key

        key_hash = hash_key(raw)
        record = ApiKey(name=name, user_id=user_id, role="admin", key_hash=key_hash)
        self.auth.keys[record.key_id] = record
        self.auth._by_hash[key_hash] = record.key_id

    def register(
        self,
        instance: Any,
        *,
        name: str | None = None,
        project_id: str = "default",
    ) -> Registered:
        """Register an SDK object; attaches platform storage and observability."""
        if self.storage is not None and getattr(instance, "storage", None) is None:
            instance.storage = self.storage
        if getattr(instance, "observer", None) is None:
            instance.observer = self.monitoring.observer()
        return self.registry.register(instance, name=name, project_id=project_id)

    def create_app(self) -> FastAPI:
        return self.app

    # -- auth dependencies ----------------------------------------------------

    def _require_api_key(self, x_api_key: str | None = Header(default=None)) -> Principal:
        if not self.auth_enabled:
            return Principal(user_id="anonymous", role="admin", key_id="none")
        principal = self.auth.authenticate(x_api_key)
        if principal is None:
            raise HTTPException(status_code=401, detail="missing or invalid API key")
        return principal

    def _require_admin(self, x_api_key: str | None = Header(default=None)) -> Principal:
        principal = self._require_api_key(x_api_key)
        if principal.role != "admin":
            raise HTTPException(status_code=403, detail="requires admin role")
        return principal

    # -- helpers ----------------------------------------------------------------

    def _entry(self, name: str) -> Registered:
        try:
            return self.registry.get(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @staticmethod
    def _response_payload(instance: Any, result: Any) -> dict[str, Any]:
        payload = result.model_dump()
        payload["session_id"] = getattr(instance, "session_id", None)
        return payload

    def _resolve_session(self, instance: Any, requested: str | None) -> None:
        """Point the instance at a session (recovered from storage when set)."""
        current = getattr(instance, "session_id", None)
        if requested:
            instance.session_id = requested
        elif not current:
            instance.session_id = uuid.uuid4().hex[:12]

    # -- routes -----------------------------------------------------------------

    def _register_routes(self) -> None:
        app = self.app

        @app.get("/healthz")
        def healthz() -> dict[str, str]:
            return {"status": "ok", "agents": str(len(self.registry.entries))}

        # -- agents ------------------------------------------------------------

        @app.post("/api/agents")
        def create_agent(
            request: AgentCreate,
            principal: Principal = Depends(self._require_admin),
        ) -> dict[str, Any]:
            """Create and register a platform-managed agent from config."""
            if request.name in self.registry.entries:
                raise HTTPException(status_code=409, detail=f"agent '{request.name}' exists")
            try:
                from fakzed.model import create_model

                extras: dict[str, Any] = {}
                if request.api_key is not None:
                    extras["api_key"] = request.api_key
                if request.base_url is not None:
                    extras["base_url"] = request.base_url
                model = create_model(request.model, **extras)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            agent = Agent(
                name=request.name,
                description=request.description,
                instructions=request.instructions,
                model=model,
            )
            entry = self.register(agent, project_id=request.project_id)
            return entry.model_dump(exclude={"instance"})

        @app.get("/api/agents")
        def list_agents(
            principal: Principal = Depends(self._require_api_key),
        ) -> list[dict[str, Any]]:
            return [e.model_dump(exclude={"instance"}) for e in self.registry.list()]

        @app.get("/api/agents/{name}")
        def get_agent(
            name: str, principal: Principal = Depends(self._require_api_key)
        ) -> dict[str, Any]:
            return self._entry(name).model_dump(exclude={"instance"})

        @app.patch("/api/agents/{name}")
        def patch_agent(
            name: str,
            patch: AgentPatch,
            principal: Principal = Depends(self._require_admin),
        ) -> dict[str, Any]:
            entry = self._entry(name)
            if patch.enabled is not None:
                entry.enabled = patch.enabled
            return entry.model_dump(exclude={"instance"})

        @app.delete("/api/agents/{name}")
        def delete_agent(
            name: str, principal: Principal = Depends(self._require_admin)
        ) -> dict[str, bool]:
            return {"unregistered": self.registry.unregister(name)}

        # -- chat --------------------------------------------------------------

        @app.post("/api/agents/{name}/chat")
        def chat(
            name: str,
            request: ChatRequest,
            principal: Principal = Depends(self._require_api_key),
        ) -> dict[str, Any]:
            entry = self._entry(name)
            with entry._lock:
                instance = entry.instance
                self._resolve_session(instance, request.session_id)
                result = instance.run(
                    request.message,
                    context=request.context,
                    stop_after_tool_call=request.stop_after_tool_call,
                )
            return self._response_payload(instance, result)

        @app.post("/api/agents/{name}/chat/stream")
        def chat_stream(
            name: str, request: ChatRequest, principal: Principal = Depends(self._require_api_key)
        ) -> StreamingResponse:
            entry = self._entry(name)

            def generate() -> Iterator[str]:
                with entry._lock:
                    instance = entry.instance
                    self._resolve_session(instance, request.session_id)
                    for event in instance.run_stream(request.message, context=request.context):
                        data = self._response_payload(instance, event)
                        yield f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")

        @app.post("/api/agents/{name}/resume")
        def resume(
            name: str, principal: Principal = Depends(self._require_api_key)
        ) -> dict[str, Any]:
            entry = self._entry(name)
            with entry._lock:
                result = entry.instance.resume()
            return self._response_payload(entry.instance, result)

        # -- sessions -----------------------------------------------------------

        @app.get("/api/sessions/{session_id}")
        def get_session(
            session_id: str, principal: Principal = Depends(self._require_api_key)
        ) -> dict[str, Any]:
            for entry in self.registry.list():
                storage = getattr(entry.instance, "storage", None)
                if storage is None:
                    continue
                row = storage.read_session(session_id)
                if row is not None:
                    return row.model_dump()
            raise HTTPException(status_code=404, detail="session not found")

        # -- runs ----------------------------------------------------------------

        @app.post("/api/runs")
        def create_run(
            request: RunRequest, principal: Principal = Depends(self._require_api_key)
        ) -> dict[str, Any]:
            self._entry(request.agent)  # 404 before submitting
            record = self.runs.submit(request.agent, request.message, session_id=request.session_id)
            return record.model_dump()

        @app.get("/api/runs")
        def list_runs(
            principal: Principal = Depends(self._require_api_key),
        ) -> list[dict[str, Any]]:
            return [r.model_dump() for r in self.runs.list()]

        @app.get("/api/runs/{run_id}")
        def get_run(
            run_id: str, principal: Principal = Depends(self._require_api_key)
        ) -> dict[str, Any]:
            record = self.runs.get(run_id)
            if record is None:
                raise HTTPException(status_code=404, detail="run not found")
            return record.model_dump()

        @app.post("/api/runs/{run_id}/cancel")
        def cancel_run(
            run_id: str, principal: Principal = Depends(self._require_api_key)
        ) -> dict[str, bool]:
            return {"cancelled": self.runs.cancel(run_id)}

        # -- monitoring ------------------------------------------------------------

        @app.get("/api/events")
        def events(
            principal: Principal = Depends(self._require_api_key),
        ) -> list[dict[str, Any]]:
            return [e.model_dump() for e in self.monitoring.recent_events()]

        @app.get("/api/traces")
        def traces(
            principal: Principal = Depends(self._require_api_key),
        ) -> list[dict[str, Any]]:
            return [t.model_dump() for t in self.monitoring.traces()]

        @app.get("/api/metrics/summary")
        def metrics_summary(
            principal: Principal = Depends(self._require_api_key),
        ) -> dict:
            return self.monitoring.summary()

        # -- tenancy --------------------------------------------------------------

        @app.post("/api/tenants/users")
        def create_user(
            request: TenantRequest,
            principal: Principal = Depends(self._require_admin),
        ) -> dict[str, Any]:
            return self.tenants.create_user(request.name, email=request.email).model_dump()

        @app.post("/api/tenants/orgs")
        def create_org(
            request: TenantRequest,
            principal: Principal = Depends(self._require_admin),
        ) -> dict[str, Any]:
            return self.tenants.create_org(request.name, owner_id=principal.user_id).model_dump()

        @app.get("/api/tenants/orgs")
        def list_orgs(
            principal: Principal = Depends(self._require_api_key),
        ) -> list[dict[str, Any]]:
            return [o.model_dump() for o in self.tenants.orgs.values()]

        @app.post("/api/tenants/projects")
        def create_project(
            request: TenantRequest,
            principal: Principal = Depends(self._require_admin),
        ) -> dict[str, Any]:
            org_id = request.org_id
            if org_id is None:
                orgs = self.tenants.orgs_of(principal.user_id)
                if not orgs:
                    raise HTTPException(status_code=400, detail="no organization; create one first")
                org_id = orgs[0].org_id
            return self.tenants.create_project(org_id, request.name).model_dump()

        @app.get("/api/tenants/orgs/{org_id}/projects")
        def list_projects(
            org_id: str, principal: Principal = Depends(self._require_api_key)
        ) -> list[dict[str, Any]]:
            return [p.model_dump() for p in self.tenants.projects_of(org_id)]

        # -- api keys ---------------------------------------------------------------

        @app.post("/api/keys")
        def issue_key(
            request: KeyRequest,
            principal: Principal = Depends(self._require_admin),
        ) -> dict[str, Any]:
            if request.role not in ("user", "admin"):
                raise HTTPException(status_code=400, detail="role must be 'user' or 'admin'")
            user_id = request.user_id or principal.user_id
            raw, record = self.auth.issue(name=request.name, user_id=user_id, role=request.role)
            payload = record.model_dump(exclude={"key_hash"})
            payload["api_key"] = raw  # returned exactly once
            return payload

        @app.delete("/api/keys/{key_id}")
        def revoke_key(
            key_id: str, principal: Principal = Depends(self._require_admin)
        ) -> dict[str, bool]:
            return {"revoked": self.auth.revoke(key_id)}
