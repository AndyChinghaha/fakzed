"""A minimal MCP stdio echo server used by tests (mcp 2.x API)."""

import asyncio

from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def echo(text: str) -> str:
    """Echo the given text back."""
    return f"echo: {text}"


@server.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
