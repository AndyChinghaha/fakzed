"""Network-path tests for the three HTTP providers, using fake clients.

Covers response / response_stream (sync + async) plus tool-call parsing and
structured output, without any real network access.
"""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from fakzed.model import Message
from fakzed.model.provider import AnthropicChat, OllamaChat, OpenAIChat

# -- wire object helpers -------------------------------------------------------


def openai_raw(content: str = "hi", tool_calls: Any = None, usage: Any = None) -> Any:
    msg = SimpleNamespace(content=content, reasoning_content=None, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def openai_usage() -> Any:
    return SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=2),
    )


def openai_chunk(delta: Any) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


class _FakeOpenAI:
    def __init__(self, result: Any, stream: Any = None) -> None:
        self._result = result
        self._stream = stream
        self.kwargs: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._stream if kwargs.get("stream") else self._result


class _AsyncIter:
    """Wrap a sync iterable so it satisfies `async for`."""

    def __init__(self, items: Any) -> None:
        self._it = iter(items)

    def __aiter__(self) -> "_AsyncIter":
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeOpenAIAsync:
    def __init__(self, result: Any = None, stream: Any = None) -> None:
        self._result = result
        self._stream = stream
        self.kwargs: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return _AsyncIter(self._stream) if kwargs.get("stream") else self._result


# -- OpenAI --------------------------------------------------------------------


def test_openai_response_and_tool_calls() -> None:
    fn = SimpleNamespace(name="calc", arguments='{"expr": "1+1"}')
    raw = openai_raw(
        content="", tool_calls=[SimpleNamespace(id="c1", function=fn)], usage=openai_usage()
    )
    model = OpenAIChat(id="gpt-4o", api_key="k")
    model._client = _FakeOpenAI(raw)  # noqa: SLF001

    result = model.response([Message(role="user", content="1+1")])

    assert result.tool_calls is not None and result.tool_calls[0].name == "calc"
    assert result.usage is not None and result.usage.total_tokens == 15
    assert model._client.kwargs["model"] == "gpt-4o"  # noqa: SLF001


def test_openai_response_structured_output() -> None:
    class CityWeather(BaseModel):
        city: str
        temperature: float

    raw = openai_raw(content='{"city": "Beijing", "temperature": 25.0}')
    model = OpenAIChat(id="gpt-4o", api_key="k")
    model._client = _FakeOpenAI(raw)  # noqa: SLF001

    result = model.response([Message(role="user", content="weather")], response_format=CityWeather)

    assert result.parsed is not None
    assert result.parsed.city == "Beijing"
    assert result.parsed.temperature == 25.0


def test_openai_response_stream_aggregates() -> None:
    chunks = [
        openai_chunk(SimpleNamespace(content="Hel", reasoning_content=None, tool_calls=None)),
        openai_chunk(SimpleNamespace(content="lo", reasoning_content=None, tool_calls=None)),
    ]
    model = OpenAIChat(id="gpt-4o", api_key="k")
    model._client = _FakeOpenAI(None, stream=iter(chunks))  # noqa: SLF001

    events = list(model.response_stream([Message(role="user", content="hi")]))

    assert events[-1].event == "complete"
    assert events[-1].content == "Hello"


def test_openai_async_paths() -> None:
    async def main() -> None:
        raw = openai_raw(content="async hi", usage=openai_usage())
        model = OpenAIChat(id="gpt-4o", api_key="k")
        model._async_client = _FakeOpenAIAsync(raw)  # noqa: SLF001
        result = await model.aresponse([Message(role="user", content="hi")])
        assert result.content == "async hi"

        model._async_client = _FakeOpenAIAsync(  # noqa: SLF001
            stream=[
                openai_chunk(SimpleNamespace(content="a", reasoning_content=None, tool_calls=None))
            ]
        )
        events = [e async for e in model.aresponse_stream([Message(role="user", content="hi")])]
        assert events[-1].content == "a"

    asyncio.run(main())


# -- Anthropic -----------------------------------------------------------------


class _FakeAnthropic:
    def __init__(self, result: Any = None, stream_events: Any = None) -> None:
        self._result = result
        self._stream_events = stream_events
        self.kwargs: dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._result

    @contextmanager
    def _stream(self, **kwargs: Any):
        yield self._stream_events


def test_anthropic_response() -> None:
    raw = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="claude says hi")],
        usage=SimpleNamespace(input_tokens=4, output_tokens=3),
    )
    model = AnthropicChat(id="claude-3", api_key="k")
    model._client = _FakeAnthropic(result=raw)  # noqa: SLF001

    result = model.response([Message(role="user", content="hi")])

    assert result.content == "claude says hi"
    assert result.usage is not None and result.usage.input_tokens == 4


def test_anthropic_stream_with_tool_use() -> None:
    events = [
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="tool_use", id="t1", name="lookup", index=0),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"q":'),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json='"x"}'),
        ),
        SimpleNamespace(
            type="message_delta", usage=SimpleNamespace(input_tokens=5, output_tokens=2)
        ),
    ]
    model = AnthropicChat(id="claude-3", api_key="k")
    model._client = _FakeAnthropic(stream_events=iter(events))  # noqa: SLF001

    results = list(model.response_stream([Message(role="user", content="go")]))

    assert results[-1].event == "complete"
    assert results[-1].tool_calls[0].name == "lookup"
    assert results[-1].tool_calls[0].arguments == {"q": "x"}


class _FakeAnthropicAsync:
    def __init__(self, result: Any = None) -> None:
        self._result = result
        self.kwargs: dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._result


def test_anthropic_async_response() -> None:
    async def main() -> None:
        raw = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="async claude")],
            usage=SimpleNamespace(input_tokens=4, output_tokens=3),
        )
        model = AnthropicChat(id="claude-3", api_key="k")
        model._async_client = _FakeAnthropicAsync(result=raw)  # noqa: SLF001
        result = await model.aresponse([Message(role="user", content="hi")])
        assert result.content == "async claude"

    asyncio.run(main())


# -- Ollama --------------------------------------------------------------------


class _FakeOllama:
    def __init__(self, result: Any = None, stream: Any = None) -> None:
        self._result = result
        self._stream = stream
        self.kwargs: dict[str, Any] = {}

    def chat(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._stream if kwargs.get("stream") else self._result


def test_ollama_response_and_usage() -> None:
    raw = SimpleNamespace(
        message=SimpleNamespace(content="local llama", thinking=None, tool_calls=None),
        prompt_eval_count=12,
        eval_count=7,
    )
    model = OllamaChat(id="llama3", host="http://127.0.0.1:11434")
    model._client = _FakeOllama(result=raw)  # noqa: SLF001

    result = model.response([Message(role="user", content="hi")])

    assert result.content == "local llama"
    assert result.usage is not None and result.usage.total_tokens == 19


def test_ollama_stream_with_tool_calls() -> None:
    tc = SimpleNamespace(
        id="c1",
        index=0,
        function=SimpleNamespace(name="calc", arguments='{"expr": "2+2"}'),
    )
    chunks = [
        SimpleNamespace(message=SimpleNamespace(content="", thinking=None, tool_calls=[tc])),
        SimpleNamespace(
            message=SimpleNamespace(content="done", thinking=None, tool_calls=None),
            prompt_eval_count=3,
            eval_count=1,
        ),
    ]
    model = OllamaChat(id="llama3")
    model._client = _FakeOllama(stream=iter(chunks))  # noqa: SLF001

    results = list(model.response_stream([Message(role="user", content="calc")]))

    assert results[-1].content == "done"
    assert results[-1].tool_calls[0].name == "calc"
    assert results[-1].tool_calls[0].arguments == {"expr": "2+2"}
