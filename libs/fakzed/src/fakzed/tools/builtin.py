"""Built-in tools: calculator, file I/O, shell, URL fetch, and web search.

All are plain `@tool` functions — usable standalone or bundled into a
`ToolKit`. Dangerous tools (shell, file writes) carry `dangerous=True` so the
agent's `tool_permission_handler` can gate them.
"""

import ast
import json
import operator
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fakzed.tools.tool import Tool, tool

# -- calculator ----------------------------------------------------------------

_BIN_OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _safe_eval(node: ast.AST) -> int | float:
    """Evaluate an AST restricted to arithmetic — no calls, no names."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_safe_eval(node.operand)
    raise ValueError("unsupported expression (only arithmetic is allowed)")


@tool
def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression: + - * / // % ** and parentheses.

    Safe: only arithmetic AST nodes are allowed; function calls, attribute
    access, and names are rejected.
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree)
        return str(result)
    except (ValueError, SyntaxError, ZeroDivisionError) as exc:
        return f"Error: {exc}"


# -- file I/O -------------------------------------------------------------------

_MAX_READ_BYTES = 512 * 1024  # 512 KB safety cap for reads


@tool
def read_file(path: str) -> str:
    """Read a text file from the local filesystem and return its contents."""
    file = Path(path)
    if not file.is_file():
        return f"Error: file not found: {path}"
    if file.stat().st_size > _MAX_READ_BYTES:
        return f"Error: file too large (>{_MAX_READ_BYTES} bytes): {path}"
    return file.read_text(encoding="utf-8", errors="replace")


@tool(dangerous=True)
def write_file(path: str, content: str) -> str:
    """Write text content to a file (creates parent directories).

    Dangerous: overwrites existing files. Requires permission approval when a
    `tool_permission_handler` is configured on the agent.
    """
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding="utf-8")
    return f"Wrote {file.stat().st_size} bytes to {path}"


# -- shell ---------------------------------------------------------------------


@tool(dangerous=True)
def run_shell(command: str) -> str:
    """Run a shell command and return stdout/stderr.

    Dangerous: arbitrary command execution. Requires permission approval when
    a `tool_permission_handler` is configured on the agent.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30s"
    output = result.stdout.strip() or result.stderr.strip()
    return output or f"(exit code {result.returncode})"


# -- URL fetch ------------------------------------------------------------------

_MAX_URL_BYTES = 1024 * 1024  # 1 MB safety cap for fetched pages


@tool
def url_read(url: str) -> str:
    """Fetch a URL over HTTP(S) and return its text content (HTML or plain)."""
    request = urllib.request.Request(url, headers={"User-Agent": "fakzed/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            content = response.read(_MAX_URL_BYTES + 1)
    except Exception as exc:  # noqa: BLE001
        return f"Error: could not fetch {url}: {exc}"
    if len(content) > _MAX_URL_BYTES:
        return f"Error: response too large (>{_MAX_URL_BYTES} bytes)"
    return content.decode("utf-8", errors="replace")


# -- web search -----------------------------------------------------------------

_DDG_RESULT_RE = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>')
_DDG_SNIPPET_RE = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>')


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo and return titles, links, and snippets.

    Note: relies on DuckDuckGo's public HTML endpoint (no API key needed);
    formatting of that endpoint may change over time.
    """
    data = urllib.parse.urlencode({"q": query}).encode()
    request = urllib.request.Request(
        "https://html.duckduckgo.com/html/",
        data=data,
        headers={"User-Agent": "Mozilla/5.0 (fakzed)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return f"Error: search failed: {exc}"

    titles = [(_strip_tags(t), url) for url, t in _DDG_RESULT_RE.findall(html)]
    snippets = [_strip_tags(s) for s in _DDG_SNIPPET_RE.findall(html)]
    results = []
    for i, (title, url) in enumerate(titles[:max_results]):
        results.append(
            {
                "title": title,
                "url": _unescape_url(url),
                "snippet": snippets[i] if i < len(snippets) else "",
            }
        )
    if not results:
        return "No results found."
    return json.dumps(results, ensure_ascii=False, indent=2)


def _unescape_url(url: str) -> str:
    """Strip DuckDuckGo's redirect wrapper and decode HTML entities."""
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query:
        url = query["uddg"][0]
    return re.sub(r"&amp;", "&", url)


__all__: list[str] = [
    "calculator",
    "read_file",
    "write_file",
    "run_shell",
    "url_read",
    "web_search",
]


def get_builtin_tools() -> list[Tool]:
    """All built-in tools as a list (convenience for bundling)."""
    return [calculator, read_file, write_file, run_shell, url_read, web_search]
