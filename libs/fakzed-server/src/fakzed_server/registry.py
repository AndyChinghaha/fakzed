"""Agent registry: a single place to register SDK objects on the platform.

The same registration mechanism is shared between the SDK and the platform:
an Agent (or Team/Workflow) created locally is `register`-ed here and then
served over HTTP, while a `RemoteAgent` on the SDK side calls it back by name.
"""

from __future__ import annotations

import threading
from typing import Any, Protocol

from pydantic import BaseModel, Field, PrivateAttr


class Registered(BaseModel):
    """Metadata for one registered SDK object."""

    name: str
    kind: str
    description: str | None = None
    project_id: str = "default"
    enabled: bool = True
    instance: Any = Field(exclude=True)

    #: Serializes requests touching the instance (session state is mutable).
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)


class RegistryEntry(Protocol):
    """Minimal protocol any registrable SDK object must satisfy."""

    name: str | None
    description: str | None

    def run(self, message: Any, **kwargs: Any) -> Any: ...
    def arun(self, message: Any, **kwargs: Any) -> Any: ...
    def resume(self) -> Any: ...
    def aresume(self) -> Any: ...
    def run_stream(self, message: Any, **kwargs: Any) -> Any: ...
    def arun_stream(self, message: Any, **kwargs: Any) -> Any: ...


class AgentRegistry(BaseModel):
    """Name-addressed registry of SDK objects (Agent/Team/Workflow)."""

    entries: dict[str, Registered] = Field(default_factory=dict)

    def register(
        self,
        instance: Any,
        *,
        name: str | None = None,
        project_id: str = "default",
    ) -> Registered:
        """Register an SDK object under `name` (defaults to instance.name).

        Re-registering under the same name replaces the previous entry.
        """
        resolved = name or getattr(instance, "name", None)
        if not resolved:
            raise ValueError("register requires a name (set instance.name or pass name=)")
        kind = type(instance).__name__
        entry = Registered(
            name=resolved,
            kind=kind,
            description=getattr(instance, "description", None),
            project_id=project_id,
            instance=instance,
        )
        self.entries[resolved] = entry
        return entry

    def get(self, name: str) -> Registered:
        entry = self.entries.get(name)
        if entry is None:
            raise KeyError(f"no agent registered as '{name}'")
        if not entry.enabled:
            raise PermissionError(f"agent '{name}' is disabled")
        return entry

    def unregister(self, name: str) -> bool:
        return self.entries.pop(name, None) is not None

    def list(self, project_id: str | None = None) -> list[Registered]:
        """List registered entries, optionally filtered by project."""
        entries = list(self.entries.values())
        if project_id is not None:
            entries = [e for e in entries if e.project_id == project_id]
        return entries
