"""Lifecycle hooks for agent and workflow runs."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Hooks(BaseModel):
    """Callbacks fired at key points of an Agent run.

    Hook signatures:
    - on_run_start(message: str) — the incoming user message
    - on_run_end(response: RunResponse) — the completed run
    - on_tool_call(call: ToolCall) — before a tool executes
    - on_tool_result(call: ToolCall, result: str) — after a tool executes
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    on_run_start: list[Callable[..., None]] = Field(default_factory=list)
    on_run_end: list[Callable[..., None]] = Field(default_factory=list)
    on_tool_call: list[Callable[..., None]] = Field(default_factory=list)
    on_tool_result: list[Callable[..., None]] = Field(default_factory=list)


def fire(hooks: list[Callable[..., None]], *args: Any) -> None:
    """Invoke every hook, swallowing individual hook errors."""
    for hook in hooks:
        try:
            hook(*args)
        except Exception:  # noqa: BLE001
            # hooks are observability conveniences; never break the run
            continue
