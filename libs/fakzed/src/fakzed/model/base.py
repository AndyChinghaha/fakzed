"""Abstract model interface over LLM providers."""

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from fakzed.model.message import Message
from fakzed.model.response import ModelResponse
from fakzed.model.tool import Tool

#: Accepted response format: a Pydantic model class or a raw JSON schema dict.
ResponseFormat = type[BaseModel] | dict[str, Any]


def _extract_json(content: str) -> str:
    """Extract the JSON payload from a model response.

    Tolerates markdown code fences and surrounding prose.
    """
    text = content.strip()
    if text.startswith("```"):
        # Strip the opening fence (```json or ```) and trailing fence.
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        fence = text.rfind("```")
        if fence != -1:
            text = text[:fence]
    return text.strip()


class Model(BaseModel, ABC):
    """Unified model interface.

    Concrete adapters convert between `Message`/`Tool` and the provider's
    native wire format. Implementations live in `fakzed.model.provider`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    #: Model identifier, e.g. "deepseek-chat".
    id: str
    #: Provider name, e.g. "openai", "deepseek", "anthropic", "ollama".
    provider: str
    name: str | None = None
    api_key: str | None = None

    def get_api_key(self) -> str | None:
        return self.api_key

    # -- structured output helpers ------------------------------------------

    def _normalize_schema(self, response_format: ResponseFormat) -> dict[str, Any]:
        """Turn a Pydantic class or dict into a JSON schema dict."""
        if isinstance(response_format, dict):
            return response_format
        return response_format.model_json_schema()

    def _inject_schema(self, messages: Sequence[Message], schema: dict[str, Any]) -> list[Message]:
        """Append a system instruction asking the model to emit matching JSON."""
        prompt = "Respond with a JSON object matching this JSON schema:\n" + json.dumps(
            schema, ensure_ascii=False
        )
        return [*messages, Message(role="system", content=prompt)]

    def _prepare_messages(
        self, messages: Sequence[Message], schema: dict[str, Any] | None
    ) -> list[Message]:
        """Inject the schema prompt when the provider lacks native support."""
        if schema is None or self._supports_native_json_schema():
            return list(messages)
        return self._inject_schema(messages, schema)

    def _supports_native_json_schema(self) -> bool:
        return False

    def _build_response_format(self, schema: dict[str, Any] | None) -> Any | None:
        """Return the provider-native response_format value, or None."""
        return None

    def _parse_structured(self, content: str, response_format: ResponseFormat) -> Any:
        """Parse model content into the requested structured type."""
        data = json.loads(_extract_json(content))
        if isinstance(response_format, dict):
            return data
        return response_format.model_validate(data)

    # -- abstract API -------------------------------------------------------

    @abstractmethod
    def response(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Send messages and return a single complete response."""

    @abstractmethod
    def response_stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> Iterator[ModelResponse]:
        """Send messages and yield streamed response events."""

    @abstractmethod
    async def aresponse(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Async variant of `response`."""

    @abstractmethod
    def aresponse_stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelResponse]:
        """Async variant of `response_stream`.

        Not an `async def` on purpose: it returns an async iterator that is
        consumed with `async for`, which matches async-generator implementations
        in subclasses.
        """
