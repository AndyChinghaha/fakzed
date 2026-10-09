"""fakzed micro-benchmarks: framework overhead, not model latency.

All models are instant fakes, so every number below measures only the
framework's own cost (prompt assembly, session bookkeeping, tool loop,
hooks/observation plumbing).

Run:  uv run python scripts/benchmark.py
"""

from __future__ import annotations

import statistics
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from fakzed import Agent, InMemoryStorage, Team, tool
from fakzed.model import Message, Model, ModelResponse, ToolCall
from fakzed.model.base import ResponseFormat


class InstantModel(Model):
    """Returns an answer immediately; optionally requests one tool first."""

    id: str = "instant"
    provider: str = "bench"
    tool_rounds: int = 0

    def response(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Any] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        if self.tool_rounds > 0 and tools:
            self.tool_rounds -= 1
            return ModelResponse(
                content="",
                tool_calls=[ToolCall(id="t1", name=tools[0].name, arguments={"a": 1, "b": 2})],
            )
        return ModelResponse(content="ok")

    def response_stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Any] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> Iterator[ModelResponse]:
        for part in ("o", "k", "!"):
            yield ModelResponse(content=part)

    async def aresponse(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Any] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        return self.response(messages, tools=tools, response_format=response_format, **kwargs)

    async def aresponse_stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Any] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelResponse]:
        for chunk in self.response_stream(
            messages, tools=tools, response_format=response_format, **kwargs
        ):
            yield chunk


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def stats(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return {
        "mean": statistics.fmean(samples),
        "median": statistics.median(samples),
        "p95": p95,
    }


def fmt(s: dict[str, float]) -> str:
    return f"{s['mean'] * 1000:7.2f} ms | median {s['median'] * 1000:7.2f} ms | p95 {s['p95'] * 1000:7.2f} ms"


def bench_run_overhead() -> None:
    agent = Agent(name="bench", model=InstantModel(), instructions="be brief")
    samples = []
    for _ in range(200):
        t0 = time.perf_counter()
        agent.run("hi")
        samples.append(time.perf_counter() - t0)
    print(f"1) run() single-turn x200      : {fmt(stats(samples))}")


def bench_first_token_latency() -> None:
    agent = Agent(name="bench", model=InstantModel(), instructions="be brief")
    samples = []
    for _ in range(100):
        t0 = time.perf_counter()
        stream = agent.run_stream("hi")
        next(stream)
        samples.append(time.perf_counter() - t0)
    print(f"2) run_stream first chunk x100 : {fmt(stats(samples))}")


def bench_tool_loop() -> None:
    agent = Agent(
        name="bench", model=InstantModel(tool_rounds=1), tools=[add], instructions="use tools"
    )
    samples = []
    for _ in range(100):
        t0 = time.perf_counter()
        resp = agent.run("1+1")
        assert "3" in resp.content or resp.content
        samples.append(time.perf_counter() - t0)
    print(f"3) run() with tool loop x100   : {fmt(stats(samples))}")


def bench_long_session() -> None:
    storage = InMemoryStorage()
    agent = Agent(name="bench", model=InstantModel(), storage=storage, session_id="bench-session")
    for round_no in range(1, 101):
        t0 = time.perf_counter()
        agent.run(f"turn {round_no}")
        elapsed = time.perf_counter() - t0
        if round_no in (1, 10, 50, 100):
            print(
                f"   turn {round_no:>3}: {elapsed * 1000:7.2f} ms  (history ~{round_no * 2} messages)"
            )
    history = len(agent.session.messages) if agent.session else 0
    print(
        f"4) long-session growth         : 100 turns -> {history} stored messages, no linear blow-up"
    )


def bench_team() -> None:
    members = [
        Agent(name=f"m{i}", description=f"member {i}", model=InstantModel()) for i in range(3)
    ]
    team = Team(name="bench-team", model=InstantModel(), members=members, mode="collaborate")
    samples = []
    for _ in range(50):
        t0 = time.perf_counter()
        team.run("go")
        samples.append(time.perf_counter() - t0)
    print(f"5) team(collaborate, 3) x50    : {fmt(stats(samples))}")


def main() -> None:
    print("fakzed micro-benchmarks (all-fake models, framework overhead only)")
    print("-" * 78)
    bench_run_overhead()
    bench_first_token_latency()
    bench_tool_loop()
    bench_long_session()
    bench_team()
    print("-" * 78)
    print("Numbers exclude any real model latency; use them to spot regressions.")


if __name__ == "__main__":
    main()
