"""Built-in tool tests: calculator, file I/O, shell, URL fetch, web search."""

import urllib.request

from fakzed.tools import calculator, read_file, run_shell, url_read, web_search, write_file

# -- calculator ----------------------------------------------------------------


def test_calculator_basic_arithmetic():
    assert calculator.call({"expression": "1 + 2 * 3"}) == "7"
    assert calculator.call({"expression": "(10 - 4) / 2"}) == "3.0"
    assert calculator.call({"expression": "2 ** 10"}) == "1024"
    assert calculator.call({"expression": "-3 + 5"}) == "2"


def test_calculator_rejects_unsafe_expressions():
    for expression in ["__import__('os').system('dir')", "open('x')", "[i for i in range(10)]"]:
        result = calculator.call({"expression": expression})
        assert result.startswith("Error:"), result


def test_calculator_reports_division_by_zero():
    result = calculator.call({"expression": "1 / 0"})
    assert result.startswith("Error:")


# -- file I/O ------------------------------------------------------------------


def test_read_file(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hello fakzed", encoding="utf-8")
    assert read_file.call({"path": str(path)}) == "hello fakzed"


def test_read_file_missing():
    result = read_file.call({"path": "definitely/missing.txt"})
    assert result.startswith("Error:")


def test_write_file_creates_parents(tmp_path):
    path = tmp_path / "sub" / "dir" / "out.txt"
    result = write_file.call({"path": str(path), "content": "data"})
    assert "Wrote" in result
    assert path.read_text(encoding="utf-8") == "data"


# -- shell ---------------------------------------------------------------------


def test_run_shell_echo():
    result = run_shell.call({"command": "echo hello-from-shell"})
    assert "hello-from-shell" in result


def test_run_shell_marks_dangerous():
    assert run_shell.dangerous
    assert write_file.dangerous
    assert not calculator.dangerous


# -- URL fetch / search (network is monkeypatched) -----------------------------


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self, size: int = -1) -> bytes:
        return self._body[:size] if size >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_url_read(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=10: _FakeResponse(b"<html>hi</html>")
    )
    assert url_read.call({"url": "http://example.com"}) == "<html>hi</html>"


def test_url_read_error(monkeypatch):
    def boom(req, timeout=10):
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    result = url_read.call({"url": "http://example.com"})
    assert result.startswith("Error:")


def test_web_search_parses_results(monkeypatch):
    html = b"""
    <html><body>
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com&amp;x=1">Example Site</a>
      <a class="result__snippet">A great example snippet.</a>
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fsecond.org">Second</a>
    </body></html>
    """
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=15: _FakeResponse(html))
    result = web_search.call({"query": "example", "max_results": 5})
    assert "Example Site" in result
    assert "https://example.com" in result
    assert "A great example snippet." in result


def test_web_search_no_results(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=15: _FakeResponse(b"<html></html>")
    )
    result = web_search.call({"query": "zzz"})
    assert result == "No results found."
