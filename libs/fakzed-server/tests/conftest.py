"""Shared fixtures for fakzed-server tests: scriptable model + wired server."""

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import Field

from fakzed import Agent, InMemoryStorage
from fakzed.model import Message, Model, ModelResponse, Tool
from fakzed.model.base import ResponseFormat
from fakzed_server import FakzedServer

ADMIN_KEY = "fz_test_admin_key"


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


def auth_headers() -> dict[str, str]:
    return {"X-API-Key": ADMIN_KEY}


@pytest.fixture
def platform() -> tuple[TestClient, FakzedServer]:
    server = FakzedServer(admin_api_key=ADMIN_KEY, storage=InMemoryStorage())
    return TestClient(server.app), server


def register_echo_agent(server: FakzedServer) -> FakeModel:
    """Register a scripted agent named 'echo' and return its model."""
    model = FakeModel()
    agent = Agent(name="echo", model=model, instructions="reply briefly")
    server.register(agent)
    return model
