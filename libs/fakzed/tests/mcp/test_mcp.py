"""MCP client tests: connect to a real stdio echo server subprocess."""

import asyncio
import sys
from pathlib import Path

import pytest

from fakzed.tools import MCPServer

SERVER_PATH = Path(__file__).parent / "echo_server.py"


def test_mcp_server_full_flow():
    async def flow() -> None:
        server = MCPServer(command=sys.executable, args=[str(SERVER_PATH)])
        await server.connect()
        try:
            tools = await server.list_tools()
            names = {t.name for t in tools}
            assert {"echo", "add"} <= names

            echo = next(t for t in tools if t.name == "echo")
            assert echo.is_async
            assert await echo.acall({"text": "hello"}) == "echo: hello"

            add = next(t for t in tools if t.name == "add")
            assert await add.acall({"a": 2, "b": 3}) == "5"

            # schemas carry over from the MCP server
            assert add.parameters["type"] == "object"
        finally:
            await server.disconnect()

    asyncio.run(flow())


def test_mcp_server_requires_connect():
    server = MCPServer(command=sys.executable, args=["nonexistent.py"])
    with pytest.raises(RuntimeError, match="not connected"):
        asyncio.run(server.list_tools())


def test_mcp_server_name_prefix():
    server = MCPServer(command="x", name="files")
    fake_tool = type(
        "T", (), {"name": "read", "description": "read files", "input_schema": {"type": "object"}}
    )()
    tool = server._convert_tool(fake_tool)  # noqa: SLF001
    assert tool.name == "files:read"
