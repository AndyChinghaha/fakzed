"""Benchmark real provider paths (message conversion + response parsing).

Uses fake clients so no network is involved; measures the pure framework
overhead of the OpenAI / Anthropic / Ollama adapters and the Agent loop.
Run: uv run python scripts/benchmark_provider.py
"""

import time
from types import SimpleNamespace
from typing import Any

from fakzed import Agent
from fakzed.model import Message, ModelResponse
from fakzed.model.provider import AnthropicChat, OllamaChat, OpenAIChat

N = 2000


def timeit(label: str, fn: Any, count: int = N) -> None:
    fn()  # warmup
    start = time.perf_counter()
    for _ in range(count):
        fn()
    elapsed = (time.perf_counter() - start) / count * 1000
    print(f"{label:<45} {elapsed:>8.3f} ms/op")


# -- openai fake client --------------------------------------------------------


def openai_raw(content: str = "hi") -> Any:
    msg = SimpleNamespace(content=content, reasoning_content=None, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


class _FakeOpenAI:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        return self._result


# -- anthropic fake client -----------------------------------------------------


class _FakeAnthropic:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        return self._result


# -- ollama fake client --------------------------------------------------------


class _FakeOllama:
    def __init__(self, result: Any) -> None:
        self._result = result

    def chat(self, **kwargs: Any) -> Any:
        return self._result


short = [Message(role="system", content="You are a helper."), Message(role="user", content="hi")]
long_convo = short + [Message(role="user", content=f"turn {i}") for i in range(50)]


def main() -> None:
    print("== provider response path (message conversion + parse) ==")
    openai = OpenAIChat(id="gpt-4o", api_key="k")
    openai._client = _FakeOpenAI(openai_raw())  # noqa: SLF001
    anthropic = AnthropicChat(id="claude", api_key="k")
    anthropic._client = _FakeAnthropic(  # noqa: SLF001
        SimpleNamespace(
            content=[SimpleNamespace(type="text", text="claude hi")],
            usage=SimpleNamespace(input_tokens=4, output_tokens=3),
        )
    )
    ollama = OllamaChat(id="llama3")
    ollama._client = _FakeOllama(  # noqa: SLF001
        SimpleNamespace(message=SimpleNamespace(content="hi", thinking=None, tool_calls=None))
    )

    timeit("openai.response (2 msgs)", lambda: openai.response(short))
    timeit("openai.response (52 msgs)", lambda: openai.response(long_convo))
    timeit("anthropic.response (2 msgs)", lambda: anthropic.response(short))
    timeit("anthropic.response (52 msgs)", lambda: anthropic.response(long_convo))
    timeit("ollama.response (2 msgs)", lambda: ollama.response(short))
    timeit("ollama.response (52 msgs)", lambda: ollama.response(long_convo))

    print("== agent loop with real adapter ==")
    agent = Agent(name="bench", model=openai)
    timeit("agent.run (2-turn conversation)", lambda: agent.run("hi"), count=500)

    print("== model response construction ==")
    timeit("ModelResponse(content='hi')", lambda: ModelResponse(content="hi"), count=10000)


if __name__ == "__main__":
    main()
