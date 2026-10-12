"""Same-machine micro-benchmarks: fakzed vs LangGraph.

Measures, on one machine in one process:
  1. Declarative agent instantiation (the "hello world" of both frameworks)
  2. A single tool-calling loop with a scripted fake model (no network)
  3. Cold import time (subprocess, wall clock)
  4. Framework source size (Python lines you must trust/read)
  5. Core dependency count (supply-chain surface)

Prereqs - create a dedicated venv with both frameworks installed:
    uv venv .bench_env
    uv pip install --python .bench_env/Scripts/python.exe -e libs/fakzed langgraph langchain
    .bench_env/Scripts/python.exe scripts/benchmarks/compare_langgraph.py

Both sides are measured the same way: median wall time of N repeats.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import pathlib
import statistics
import subprocess
import sys
import time

NUMBER = 200  # repeats per timing sample for loop benchmarks
REPEATS = 5  # timing samples, median is reported


def measure_us(fn, number: int = NUMBER, repeats: int = REPEATS) -> float:
    """Median microseconds per call."""
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        for _ in range(number):
            fn()
        samples.append((time.perf_counter() - start) / number * 1e6)
    return statistics.median(samples)


def import_ms(statement: str) -> float:
    """Import wall time in ms (fresh interpreter per sample, warmed page cache)."""
    subprocess.run([sys.executable, "-c", statement], check=True, capture_output=True)  # warmup
    samples = []
    for _ in range(5):
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", statement],
            check=True,
            capture_output=True,
        )
        samples.append((time.perf_counter() - start) * 1e3)
    return statistics.median(samples)


def package_lines(*names: str) -> int:
    """Total Python source lines behind the given importable modules."""
    total = 0
    for name in names:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError, AttributeError):
            continue
        if spec is None:
            continue
        paths = list(spec.submodule_search_locations or ())
        if spec.origin:
            paths.append(spec.origin)
        for raw in paths:
            p = pathlib.Path(raw)
            if p.is_file():
                total += sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
            elif p.is_dir():
                total += sum(
                    sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
                    for f in p.rglob("*.py")
                )
    return total


def dependency_count(*names: str) -> int:
    """Union of direct runtime dependencies of the given distributions."""
    deps: set[str] = set()
    for name in names:
        try:
            for req in importlib.metadata.requires(name) or []:
                dep = req.split(";")[0].split(" ")[0]
                if dep and "extra ==" not in req:
                    deps.add(dep)
        except Exception:
            continue
    return len(deps)


def bench_fakzed() -> dict:

    from fakzed import Agent
    from fakzed.model import Model, ModelResponse, ToolCall

    class Fake(Model):
        id: str = "fake"
        provider: str = "fake"
        queue: list[ModelResponse] = []

        def response(self, messages, *, tools=None, response_format=None, **kw):
            return self.queue.pop(0) if self.queue else ModelResponse(content="")

        def response_stream(self, messages, *, tools=None, response_format=None, **kw):
            raise NotImplementedError

        async def aresponse(self, messages, *, tools=None, response_format=None, **kw):
            raise NotImplementedError

        async def aresponse_stream(self, messages, *, tools=None, response_format=None, **kw):
            raise NotImplementedError

    from fakzed import tool

    @tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    results: dict = {}

    def instantiate():
        Agent(name="bench", model="openai:gpt-4o-mini")

    results["instantiate_us"] = measure_us(instantiate)

    def run_loop():
        fake = Fake()
        fake.queue = [
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="add", arguments={"a": 1, "b": 2})],
            ),
            ModelResponse(content="3"),
        ]
        agent = Agent(name="bench", model=fake, tools=[add])
        agent.run("what is 1 + 2?")

    results["tool_loop_us"] = measure_us(run_loop, number=100, repeats=3)
    results["import_ms"] = import_ms("import fakzed")
    results["source_lines"] = package_lines("fakzed")
    results["deps"] = dependency_count("fakzed")
    return results


def bench_langgraph() -> dict:
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool

    class FakeWithTools(GenericFakeChatModel):
        """GenericFakeChatModel that accepts bind_tools (ignores tools)."""

        def bind_tools(self, tools, **kwargs):
            return self

    @tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    results: dict = {}

    def instantiate():
        create_agent("openai:gpt-4o-mini")

    results["instantiate_us"] = measure_us(instantiate)

    def run_loop():
        fake = FakeWithTools(
            messages=iter(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "add",
                                "args": {"a": 1, "b": 2},
                                "id": "c1",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="3"),
                ]
            )
        )
        agent = create_agent(fake, tools=[add])
        agent.invoke({"messages": [{"role": "user", "content": "what is 1 + 2?"}]})

    results["tool_loop_us"] = measure_us(run_loop, number=100, repeats=3)
    results["import_ms"] = import_ms("from langchain.agents import create_agent")
    results["source_lines"] = package_lines(
        "langgraph",
        "langgraph-prebuilt",
        "langgraph-checkpoint",
        "langchain",
        "langchain-core",
        "langchain-protocol",
    )
    results["deps"] = dependency_count(
        "langgraph",
        "langgraph-prebuilt",
        "langgraph-checkpoint",
        "langchain",
        "langchain-core",
        "langchain-protocol",
    )
    return results


def main() -> None:
    print(f"Python {sys.version.split()[0]}, fakzed vs LangGraph on this machine\n")
    fakzed = bench_fakzed()
    langgraph = bench_langgraph()
    print("| Metric | fakzed | LangGraph | ratio |")
    print("| --- | --- | --- | --- |")
    for key, label in [
        ("instantiate_us", "Agent instantiation"),
        ("tool_loop_us", "Single tool-call loop"),
        ("import_ms", "Import (warm cache)"),
        ("source_lines", "Framework source (lines)"),
        ("deps", "Core dependencies"),
    ]:
        fz, lg = fakzed[key], langgraph[key]
        unit = (
            "us"
            if "us" in key
            else ("ms" if "ms" in key else ("lines" if "lines" in key else "pkgs"))
        )
        ratio = f"{lg / fz:.1f}x" if fz else "n/a"
        print(f"| {label} | {fz:,.1f} {unit} | {lg:,.1f} {unit} | {ratio} |")


if __name__ == "__main__":
    main()
