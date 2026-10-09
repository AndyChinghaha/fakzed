"""Shared test fixtures: a scriptable fake model (no network)."""

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from pydantic import Field

from fakzed.model import Message, Model, ModelResponse, Tool
from fakzed.model.base import ResponseFormat


class FakeModel(Model):
    """A Model stub whose responses are scripted per test."""

    id: str = "fake-model"
    provider: str = "fake"
    responses: list[ModelResponse] = Field(default_factory=list)
    calls: list[dict[str, Any]] = Field(default_factory=list)

    def enqueue(self, *responses: ModelResponse) -> None:
        self.responses.extend(responses)

    def _pop(self, messages: Sequence[Message], tools: Sequence[Tool] | None) -> ModelResponse:
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self.responses:
            return ModelResponse(content="")
        return self.responses.pop(0)

    def response(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        return self._pop(messages, tools)

    def response_stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> Iterator[ModelResponse]:
        result = self._pop(messages, tools)
        yield ModelResponse(
            content=result.content, reasoning_content=result.reasoning_content, event="chunk"
        )
        yield result

    async def aresponse(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        return self._pop(messages, tools)

    async def aresponse_stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelResponse]:
        result = self._pop(messages, tools)
        yield ModelResponse(
            content=result.content, reasoning_content=result.reasoning_content, event="chunk"
        )
        yield result
