"""Context providers: dynamic runtime information injected into the prompt."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from pydantic import BaseModel


class ContextProvider(BaseModel, ABC):
    """Produces a context string at run time (time, calendar, GitHub, Slack...).

    Implement `get_context` for external integrations; built-ins cover the
    common cases. Attach instances via `Agent.context_providers`.
    """

    @abstractmethod
    def get_context(self) -> str | None:
        """Return the context text for this run, or None to skip injection."""


class TimeProvider(ContextProvider):
    """Injects the current local time."""

    timezone_name: str | None = None

    def get_context(self) -> str:
        now = datetime.now(timezone.utc)
        label = "UTC" if self.timezone_name is None else self.timezone_name
        return f"Current time ({label}): {now.isoformat()}"
