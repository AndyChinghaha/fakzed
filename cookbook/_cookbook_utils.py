"""Cookbook shared utilities: a scriptable fake model (no network, no API key).

Every cookbook example uses `ScriptedModel` so you can run it without any
provider credentials. To try the same code against a real provider, replace

    model = ScriptedModel([...])

with

    model = "deepseek:deepseek-chat"        # reads DEEPSEEK_API_KEY
"""

from collections.abc import Sequence
from typing import Any

from pydantic import Field

from fakzed.model import Message, Model, ModelResponse


class ScriptedModel(Model):
    """A Model stub whose responses come from a scripted queue."""

    id: str = "scripted"
    provider: str = "cookbook"
    responses: list[ModelResponse] = Field(default_factory=list)

    def _pop(self, messages: Sequence[Message], tools: Sequence | None = None) -> ModelResponse:
        return self.responses.pop(0) if self.responses else ModelResponse(content="")

    def response(self, messages, *, tools=None, response_format=None, **kwargs: Any):
        return self._pop(messages, tools)

    def response_stream(self, messages, *, tools=None, response_format=None, **kwargs: Any):
        result = self._pop(messages, tools)
        yield ModelResponse(content=result.content, event="chunk")
        yield result

    async def aresponse(self, messages, *, tools=None, response_format=None, **kwargs: Any):
        return self._pop(messages, tools)

    async def aresponse_stream(self, messages, *, tools=None, response_format=None, **kwargs: Any):
        result = self._pop(messages, tools)
        yield ModelResponse(content=result.content, event="chunk")
        yield result


def scripted(*contents: str) -> ScriptedModel:
    """Build a model that answers with `contents` in order."""
    return ScriptedModel(responses=[ModelResponse(content=c) for c in contents])
