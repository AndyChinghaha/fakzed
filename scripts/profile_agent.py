"""Profile the Agent run loop to find framework overhead hotspots.

Run: uv run python scripts/profile_agent.py
"""

import cProfile
import io
import pstats
from types import SimpleNamespace
from typing import Any

from fakzed import Agent
from fakzed.model.provider import OpenAIChat


def main() -> None:
    raw = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="hi", reasoning_content=None, tool_calls=None)
            )
        ],
        usage=None,
    )

    class _FakeOpenAI:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=self)

        def create(self, **kwargs: Any) -> Any:
            return raw

    model = OpenAIChat(id="gpt-4o", api_key="k")
    model._client = _FakeOpenAI()  # noqa: SLF001
    agent = Agent(name="bench", model=model)

    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(100):
        agent.run("hi")
    profiler.disable()

    out = io.StringIO()
    pstats.Stats(profiler, stream=out).sort_stats("cumulative").print_stats(18)
    print(out.getvalue())


if __name__ == "__main__":
    main()
