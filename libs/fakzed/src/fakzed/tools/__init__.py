"""Tool system: registration, schema generation, and built-in toolkits."""

from fakzed.tools.builtin import (
    calculator,
    get_builtin_tools,
    read_file,
    run_shell,
    url_read,
    web_search,
    write_file,
)
from fakzed.tools.mcp import MCPServer
from fakzed.tools.tool import Tool, tool
from fakzed.tools.toolkit import ToolKit

__all__ = [
    "Tool",
    "tool",
    "ToolKit",
    "MCPServer",
    "calculator",
    "read_file",
    "write_file",
    "run_shell",
    "url_read",
    "web_search",
    "get_builtin_tools",
]
