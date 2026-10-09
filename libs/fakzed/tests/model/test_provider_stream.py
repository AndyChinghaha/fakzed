"""Streaming, async, structured-output and client-construction paths for providers.

Complements test_provider_network.py with coverage for the paths that require
async iteration, context managers and lazy client construction.
"""

import asyncio
import sys
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from fakzed.model import Message
from fakzed.model.message import Attachment, ToolResult
from fakzed.model.provider import AnthropicChat, OllamaChat, OpenAIChat

# -- shared helpers ------------------------------------------------------------


def openai_raw(content: str = "hi", tool_calls: Any = None, usage: Any = None) -> Any:
    msg = SimpleNamespace(content=content, reasoning_content=None, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def openai_chunk(delta: Any, usage: Any = None) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage)


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


class _AsyncCtxIter:
    """Async context manager + async iterator, for anthropic-style streams."""

    def __init__(self, events: Any) -> None:
        self._it = iter(events)

    async def __aenter__(self) -> "_AsyncCtxIter":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def __aiter__(self) -> "_AsyncCtxIter":
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


# -- OpenAI fakes --------------------------------------------------------------


class _FakeOpenAI:
    def __init__(self, result: Any = None, stream: Any = None) -> None:
        self._result = result
        self._stream = stream
        self.kwargs: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._stream if kwargs.get("stream") else self._result


class _FakeOpenAIAsync:
    def __init__(self, result: Any = None, stream: Any = None) -> None:
        self._result = result
        self._stream = stream
        self.kwargs: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return _AsyncIter(self._stream) if kwargs.get("stream") else self._result


# -- Anthropic fakes -----------------------------------------------------------


class _FakeAnthropic:
    def __init__(self, result: Any = None, stream_events: Any = None) -> None:
        self._result = result
        self._stream_events = stream_events
        self.kwargs: dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._result

    def _stream(self, **kwargs: Any) -> _AsyncCtxIter:
        self.kwargs = kwargs
        return _AsyncCtxIter(self._stream_events)


class _FakeAnthropicAsync:
    def __init__(self, result: Any = None, stream_events: Any = None) -> None:
        self._result = result
        self._stream_events = stream_events
        self.kwargs: dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    async def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._result

    def _stream(self, **kwargs: Any) -> _AsyncCtxIter:
        self.kwargs = kwargs
        return _AsyncCtxIter(self._stream_events)


# -- Ollama fakes --------------------------------------------------------------


class _FakeOllama:
    def __init__(self, result: Any = None, stream: Any = None) -> None:
        self._result = result
        self._stream = stream
        self.kwargs: dict[str, Any] = {}

    def chat(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._stream if kwargs.get("stream") else self._result


class _FakeOllamaAsync:
    def __init__(self, result: Any = None, stream: Any = None) -> None:
        self._result = result
        self._stream = stream
        self.kwargs: dict[str, Any] = {}

    async def chat(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return _AsyncIter(self._stream) if kwargs.get("stream") else self._result


# -- lazy client construction --------------------------------------------------


def test_openai_client_lazy_construction(monkeypatch: Any) -> None:
    captured: list[dict[str, Any]] = []

    class _OpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI, AsyncOpenAI=_OpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "env-k")

    model = OpenAIChat(
        id="gpt-4o", base_url="http://b", organization="org", timeout=3, max_retries=1
    )
    assert model.get_api_key() == "env-k"

    model._get_client()  # noqa: SLF001
    model._get_async_client()  # noqa: SLF001

    assert len(captured) == 2
    assert captured[0]["api_key"] == "env-k"
    assert captured[0]["base_url"] == "http://b"
    assert captured[0]["organization"] == "org"
    assert captured[1]["max_retries"] == 1


def test_anthropic_client_lazy_construction(monkeypatch: Any) -> None:
    captured: list[dict[str, Any]] = []

    class _Anthropic:
        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_Anthropic, AsyncAnthropic=_Anthropic)
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-k")

    model = AnthropicChat(id="claude", base_url="http://b", timeout=4, max_retries=3)
    assert model.get_api_key() == "env-k"

    model._get_client()  # noqa: SLF001
    model._get_async_client()  # noqa: SLF001

    assert len(captured) == 2
    assert captured[0]["api_key"] == "env-k"
    assert captured[0]["base_url"] == "http://b"
    assert captured[1]["timeout"] == 4


def test_ollama_client_lazy_construction(monkeypatch: Any) -> None:
    captured: list[dict[str, Any]] = []

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    monkeypatch.setitem(sys.modules, "ollama", SimpleNamespace(Client=_Client, AsyncClient=_Client))

    model = OllamaChat(id="llama3", host="http://h", timeout=5, keep_alive="1m")
    assert model.get_api_key() is None

    model._get_client()  # noqa: SLF001
    model._get_async_client()  # noqa: SLF001

    assert captured[0] == {"host": "http://h", "timeout": 5}
    assert captured[1] == {"host": "http://h", "timeout": 5}


# -- OpenAI paths --------------------------------------------------------------


def test_openai_response_empty_choices() -> None:
    raw = SimpleNamespace(choices=[], usage=None)
    model = OpenAIChat(id="gpt-4o", api_key="k")
    model._client = _FakeOpenAI(raw)  # noqa: SLF001

    result = model.response([Message(role="user", content="x")])

    assert result.raw is raw
    assert result.content == ""


def test_openai_format_message_edges() -> None:
    raw = openai_raw(content="ok")
    model = OpenAIChat(id="gpt-4o", api_key="k")
    model._client = _FakeOpenAI(raw)  # noqa: SLF001

    model.response(
        [
            Message(role="user", name="alice", content="hi"),
            Message(
                role="user",
                content="img",
                attachments=[
                    Attachment(url="http://u"),
                    Attachment(content="b64", media_type="image/png"),
                ],
            ),
            Message(role="tool", tool_results=[ToolResult(tool_call_id="t", content="r")]),
            Message(role="tool", tool_results=[]),
        ]
    )

    wire = model._client.kwargs["messages"]  # noqa: SLF001
    assert wire[0] == {"role": "user", "content": "hi", "name": "alice"}
    assert wire[1]["content"] == [
        {"type": "text", "text": "img"},
        {"type": "image_url", "image_url": {"url": "http://u"}},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,b64"}},
    ]
    assert wire[2] == {"role": "tool", "tool_call_id": "t", "content": "r"}
    assert len(wire) == 3  # empty tool_results message is dropped


def test_openai_stream_with_reasoning_usage_and_tool_calls() -> None:
    usage = SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5)
    chunks = [
        openai_chunk(SimpleNamespace(content=None, reasoning_content="think", tool_calls=None)),
        openai_chunk(
            SimpleNamespace(
                content=None,
                reasoning_content=None,
                tool_calls=[
                    SimpleNamespace(
                        index=0, id="c1", function=SimpleNamespace(name="cal", arguments='{"a":')
                    )
                ],
            ),
            usage=usage,
        ),
        openai_chunk(
            SimpleNamespace(
                content=None,
                reasoning_content=None,
                tool_calls=[
                    SimpleNamespace(
                        index=0, id=None, function=SimpleNamespace(name="c", arguments='"1"}')
                    )
                ],
            )
        ),
    ]
    model = OpenAIChat(id="gpt-4o", api_key="k")
    model._client = _FakeOpenAI(stream=iter(chunks))  # noqa: SLF001

    events = list(model.response_stream([Message(role="user", content="q")]))

    assert events[-1].event == "complete"
    assert events[-1].reasoning_content == "think"
    assert events[-1].usage is not None and events[-1].usage.total_tokens == 5
    assert events[-1].tool_calls is not None
    assert events[-1].tool_calls[0].name == "calc"
    assert events[-1].tool_calls[0].arguments == {"a": "1"}


def test_openai_async_stream_structured() -> None:
    class _Plan(BaseModel):
        steps: list[str]

    async def main() -> None:
        chunk = openai_chunk(
            SimpleNamespace(
                content='{"steps": ["a", "b"]}', reasoning_content=None, tool_calls=None
            )
        )
        model = OpenAIChat(id="gpt-4o", api_key="k")
        model._async_client = _FakeOpenAIAsync(stream=[chunk])  # noqa: SLF001

        events = [
            e
            async for e in model.aresponse_stream(
                [Message(role="user", content="plan")], response_format=_Plan
            )
        ]

        assert events[-1].parsed is not None
        assert events[-1].parsed.steps == ["a", "b"]

    asyncio.run(main())


# -- Anthropic paths -----------------------------------------------------------


def test_anthropic_format_message_edges() -> None:
    raw = SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")], usage=None)
    model = AnthropicChat(id="claude", api_key="k")
    model._client = _FakeAnthropic(result=raw)  # noqa: SLF001

    model.response(
        [
            Message(role="system", content="sys"),
            Message(
                role="user",
                content="pic",
                attachments=[
                    Attachment(content="abc", media_type="image/jpeg"),
                    Attachment(url="http://x"),
                ],
            ),
            Message(role="assistant", content=""),
            Message(
                role="tool",
                content="ignored",
                tool_results=[ToolResult(tool_call_id="t9", content="res")],
            ),
        ]
    )

    assert model._client.kwargs["system"] == "sys"  # noqa: SLF001
    wire = model._client.kwargs["messages"]  # noqa: SLF001
    images = [b for b in wire[0]["content"] if b["type"] == "image"]
    assert images[0]["source"]["data"] == "abc"
    assert images[0]["source"]["media_type"] == "image/jpeg"
    assert images[1]["source"]["data"] == "http://x"
    assert wire[1]["content"] == [{"type": "text", "text": ""}]
    assert wire[2]["role"] == "user"
    assert wire[2]["content"][0]["type"] == "tool_result"
    assert wire[2]["content"][0]["tool_use_id"] == "t9"


def test_anthropic_structured_sync_and_async() -> None:
    class _Ans(BaseModel):
        ok: bool

    raw = SimpleNamespace(content=[SimpleNamespace(type="text", text='{"ok": true}')], usage=None)
    model = AnthropicChat(id="claude", api_key="k")
    model._client = _FakeAnthropic(result=raw)  # noqa: SLF001

    result = model.response([Message(role="user", content="q")], response_format=_Ans)
    assert result.parsed is not None and result.parsed.ok is True

    async def main() -> None:
        model._async_client = _FakeAnthropicAsync(result=raw)  # noqa: SLF001
        result2 = await model.aresponse([Message(role="user", content="q")], response_format=_Ans)
        assert result2.parsed is not None and result2.parsed.ok is True

    asyncio.run(main())


def test_anthropic_async_stream_full() -> None:
    async def main() -> None:
        events = [
            SimpleNamespace(
                type="content_block_start",
                content_block=SimpleNamespace(type="tool_use", id="t1", name="look", index=0),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="input_json_delta", partial_json='{"q":'),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="input_json_delta", partial_json="1}"),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=1,
                delta=SimpleNamespace(type="text_delta", text="hi"),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=1,
                delta=SimpleNamespace(type="thinking_delta", thinking="th"),
            ),
            SimpleNamespace(type="content_block_stop"),
            SimpleNamespace(
                type="message_delta", usage=SimpleNamespace(input_tokens=3, output_tokens=1)
            ),
        ]
        model = AnthropicChat(id="claude", api_key="k")
        model._async_client = _FakeAnthropicAsync(stream_events=events)  # noqa: SLF001

        out = [e async for e in model.aresponse_stream([Message(role="user", content="go")])]

        assert out[-1].event == "complete"
        assert out[-1].content == "hi"
        assert out[-1].reasoning_content == "th"
        assert out[-1].tool_calls is not None
        assert out[-1].tool_calls[0].name == "look"
        assert out[-1].tool_calls[0].arguments == {"q": 1}
        assert out[-1].usage is not None
        assert out[-1].usage.input_tokens == 3

    asyncio.run(main())


# -- Ollama paths --------------------------------------------------------------


def test_ollama_format_message_attachments_and_tool_results() -> None:
    raw = SimpleNamespace(
        message=SimpleNamespace(content="ok", thinking=None, tool_calls=None),
        prompt_eval_count=None,
        eval_count=None,
    )
    model = OllamaChat(id="llama3")
    model._client = _FakeOllama(result=raw)  # noqa: SLF001

    model.response(
        [
            Message(
                role="user",
                content="see",
                attachments=[Attachment(url="u1"), Attachment(content="b64")],
            ),
            Message(role="assistant", tool_results=[ToolResult(tool_call_id="t1", content="r1")]),
        ]
    )

    wire = model._client.kwargs["messages"]  # noqa: SLF001
    assert wire[0]["images"] == ["u1", "b64"]
    assert wire[1]["tool_call_id"] == "t1"
    assert wire[1]["content"] == "r1"


def test_ollama_structured_output_sync_and_stream() -> None:
    class _W(BaseModel):
        city: str

    raw = SimpleNamespace(
        message=SimpleNamespace(content='{"city": "x"}', thinking=None, tool_calls=None),
        prompt_eval_count=None,
        eval_count=None,
    )
    model = OllamaChat(id="llama3")
    model._client = _FakeOllama(result=raw)  # noqa: SLF001

    result = model.response([Message(role="user", content="q")], response_format=_W)
    assert result.parsed is not None and result.parsed.city == "x"

    chunks = [
        SimpleNamespace(
            message=SimpleNamespace(content='{"city": "y"}', thinking=None, tool_calls=None)
        )
    ]
    model._client = _FakeOllama(stream=chunks)  # noqa: SLF001

    out = list(model.response_stream([Message(role="user", content="q")], response_format=_W))
    assert out[-1].parsed is not None and out[-1].parsed.city == "y"


def test_ollama_async_paths() -> None:
    async def main() -> None:
        raw = SimpleNamespace(
            message=SimpleNamespace(content="async ollama", thinking="th", tool_calls=None),
            prompt_eval_count=2,
            eval_count=1,
        )
        model = OllamaChat(id="llama3")
        model._async_client = _FakeOllamaAsync(result=raw)  # noqa: SLF001

        result = await model.aresponse([Message(role="user", content="hi")])
        assert result.content == "async ollama"
        assert result.reasoning_content == "th"
        assert result.usage is not None and result.usage.total_tokens == 3

        tc = SimpleNamespace(
            id="c1", index=0, function=SimpleNamespace(name="calc", arguments='{"e": "1"}')
        )
        chunks = [
            SimpleNamespace(message=SimpleNamespace(content="", thinking=None, tool_calls=[tc])),
            SimpleNamespace(
                message=SimpleNamespace(content="r", thinking=None, tool_calls=None),
                prompt_eval_count=1,
                eval_count=1,
            ),
        ]
        model._async_client = _FakeOllamaAsync(stream=chunks)  # noqa: SLF001

        events = [e async for e in model.aresponse_stream([Message(role="user", content="c")])]
        assert events[-1].event == "complete"
        assert events[-1].content == "r"
        assert events[-1].tool_calls is not None
        assert events[-1].tool_calls[0].arguments == {"e": "1"}
        assert events[-1].usage is not None

    asyncio.run(main())


def test_ollama_stream_tool_call_json_error_fallback() -> None:
    tc = SimpleNamespace(
        id="c1", index=0, function=SimpleNamespace(name="calc", arguments="not-json")
    )
    chunks = [SimpleNamespace(message=SimpleNamespace(content="", thinking=None, tool_calls=[tc]))]
    model = OllamaChat(id="llama3")
    model._client = _FakeOllama(stream=iter(chunks))  # noqa: SLF001

    results = list(model.response_stream([Message(role="user", content="c")]))

    assert results[-1].tool_calls is not None
    assert results[-1].tool_calls[0].arguments == {"raw": "not-json"}
