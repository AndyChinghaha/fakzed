"""Tests for the executable Tool wrapper and @tool decorator."""

import asyncio

import pytest
from pydantic import ValidationError

from fakzed.tools import Tool, tool


def test_tool_decorator_builds_schema() -> None:
    @tool
    def add(a: int, b: int = 0) -> int:
        """Add two numbers."""
        return a + b

    assert isinstance(add, Tool)
    assert add.name == "add"
    assert add.description == "Add two numbers."
    schema = add.parameters
    assert schema["type"] == "object"
    assert "a" in schema["properties"]
    assert "b" in schema["properties"]
    assert add.call({"a": 1, "b": 2}) == 3


def test_tool_decorator_with_options() -> None:
    @tool(name="multiply", description="Multiply numbers.")
    def _mul(x: int, y: int) -> int:
        return x * y

    assert _mul.name == "multiply"
    assert _mul.description == "Multiply numbers."
    assert _mul.call({"x": 3, "y": 4}) == 12


def test_tool_to_model_tool() -> None:
    @tool
    def ping() -> str:
        """Ping the service."""
        return "pong"

    model_tool = ping.to_model_tool()
    assert model_tool.name == "ping"
    assert model_tool.parameters == ping.parameters


def test_tool_call_without_entrypoint_raises() -> None:
    plain = Tool(name="schema_only", description="No entrypoint.")
    try:
        plain.call({})
    except ValueError as exc:
        assert "no entrypoint" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_tool_validates_arguments() -> None:
    calls: list[tuple[int, int]] = []

    @tool
    def add(a: int, b: int = 0) -> int:
        """Add two numbers."""
        calls.append((a, b))
        return a + b

    with pytest.raises(ValidationError):
        add.call({"a": "not-an-int"})
    assert calls == []  # the entrypoint was never invoked


def test_tool_supports_async_entrypoint_sync_call() -> None:
    @tool
    async def fetch(url: str) -> str:
        """Fetch a URL."""
        await asyncio.sleep(0)
        return f"got {url}"

    assert fetch.is_async
    assert fetch.call({"url": "http://example.com"}) == "got http://example.com"


def test_tool_supports_async_entrypoint_acall() -> None:
    @tool
    async def fetch(url: str) -> str:
        """Fetch a URL."""
        await asyncio.sleep(0)
        return f"got {url}"

    assert asyncio.run(fetch.acall({"url": "http://x"})) == "got http://x"


def test_tool_dangerous_flag() -> None:
    @tool
    def safe() -> str:
        """Safe tool."""
        return "ok"

    @tool(dangerous=True)
    def shell(command: str) -> str:
        """Run a shell command."""
        return command

    assert not safe.dangerous
    assert shell.dangerous
