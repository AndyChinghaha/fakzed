"""MCP client: connect to external MCP servers and expose their tools.

Supports the stdio transport (subprocess-based servers, e.g. `npx` wrappers).
The `mcp` SDK is imported lazily inside `connect`, so importing fakzed never
pulls in the dependency until an MCP server is actually used.
"""

from contextlib import AsyncExitStack
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from fakzed.tools.tool import Tool


def _extract_text(result: Any) -> str:
    """Flatten a CallToolResult into plain text for the model."""
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    if not parts:
        return (
            "Error: MCP tool call failed" if getattr(result, "isError", False) else "(empty result)"
        )
    return "\n".join(parts)


class MCPServer(BaseModel):
    """A remote MCP server (stdio transport) whose tools agents can use.

    The MCP session is bound to the event loop it was created on: connect,
    list_tools, and tool calls must all happen inside the same running loop.
    Use the async agent path (`Agent.arun`) with MCP tools.

    Example:
        server = MCPServer(command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "."])
        await server.connect()
        tools = await server.list_tools()
        agent = Agent(model=..., tools=[*tools])
        await agent.arun("read the files")
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    name: str | None = None
    _session: Any = PrivateAttr(default=None)
    _stack: Any = PrivateAttr(default=None)

    async def connect(self) -> "MCPServer":
        """Start the subprocess and initialize the MCP session."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
        stack = AsyncExitStack()
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._stack = stack
        self._session = session
        return self

    async def disconnect(self) -> None:
        """Terminate the subprocess and close the session."""
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None

    async def list_tools(self) -> list[Tool]:
        """Fetch the server's tools, wrapped as fakzed `Tool` objects.

        The returned tools have async entrypoints; run the agent with `arun`
        so tool calls share this server's event loop.
        """
        if self._session is None:
            raise RuntimeError("MCPServer is not connected; call connect() first")
        result = await self._session.list_tools()
        return [self._convert_tool(t) for t in result.tools]

    def _convert_tool(self, mcp_tool: Any) -> Tool:
        """Wrap one MCP tool into a fakzed Tool."""
        name = f"{self.name}:{mcp_tool.name}" if self.name else mcp_tool.name

        async def entrypoint(**arguments: Any) -> str:
            if self._session is None:
                raise RuntimeError("MCPServer session lost; reconnect first")
            result = await self._session.call_tool(mcp_tool.name, arguments=arguments)
            return _extract_text(result)

        return Tool(
            name=name,
            description=mcp_tool.description or "",
            parameters=getattr(mcp_tool, "input_schema", None) or {},
            entrypoint=entrypoint,
            is_async=True,
        )
