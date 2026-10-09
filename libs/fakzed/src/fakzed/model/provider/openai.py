"""OpenAI-compatible model adapter.

Also serves as the base for other OpenAI-compatible providers (e.g. DeepSeek).
"""

import json
import os
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from fakzed.model.base import Model, ResponseFormat
from fakzed.model.message import Message, ToolCall
from fakzed.model.response import ModelResponse, Usage
from fakzed.model.tool import Tool


def _get_optional(obj: Any, attr: str, default: Any = None) -> Any:
    return getattr(obj, attr, None) or default


@dataclass
class _StreamState:
    """Aggregation state shared by sync and async streaming loops."""

    content_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)
    tool_calls_acc: dict[int, dict[str, Any]] = field(default_factory=dict)
    usage: Usage | None = None


class OpenAIChat(Model):
    """Adapter for OpenAI and OpenAI-compatible APIs."""

    provider: str = "openai"
    base_url: str | None = None
    organization: str | None = None
    timeout: float | None = None
    max_retries: int = 2
    _client: Any = None
    _async_client: Any = None

    def get_api_key(self) -> str | None:
        return self.api_key or os.getenv("OPENAI_API_KEY")

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.get_api_key(),
                base_url=self.base_url,
                organization=self.organization,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        return self._client

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            from openai import AsyncOpenAI

            self._async_client = AsyncOpenAI(
                api_key=self.get_api_key(),
                base_url=self.base_url,
                organization=self.organization,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        return self._async_client

    # -- message conversion -------------------------------------------------

    def _format_message(self, message: Message) -> list[dict[str, Any]]:
        """Convert one Message into one or more OpenAI wire messages.

        Tool results become one "tool" role message per result.
        """
        if message.role == "tool":
            result = message.tool_results[0] if message.tool_results else None
            if result is not None:
                return [
                    {
                        "role": "tool",
                        "tool_call_id": result.tool_call_id,
                        "content": result.content,
                    }
                ]
            return []

        wire: dict[str, Any] = {"role": message.role, "content": message.content or ""}
        if message.name:
            wire["name"] = message.name
        if message.attachments:
            wire["content"] = self._format_content(message)
        if message.tool_calls:
            wire["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in message.tool_calls
            ]
        return [wire]

    def _format_content(self, message: Message) -> list[dict[str, Any]]:
        """Build a multimodal content list when attachments are present."""
        parts: list[dict[str, Any]] = []
        if message.content:
            parts.append({"type": "text", "text": message.content})
        for attachment in message.attachments or []:
            if attachment.url:
                parts.append({"type": "image_url", "image_url": {"url": attachment.url}})
            elif attachment.content:
                prefix = f"data:{attachment.media_type};base64," if attachment.media_type else ""
                parts.append(
                    {"type": "image_url", "image_url": {"url": prefix + attachment.content}}
                )
        return parts

    def _format_messages(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        wire_messages: list[dict[str, Any]] = []
        for message in messages:
            wire_messages.extend(self._format_message(message))
        return wire_messages

    def _format_tools(self, tools: Sequence[Tool] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [tool.to_schema() for tool in tools]

    # -- structured output ---------------------------------------------------

    def _supports_native_json_schema(self) -> bool:
        return True

    def _build_response_format(self, schema: dict[str, Any] | None) -> dict[str, Any] | None:
        """OpenAI structured outputs (json_schema mode)."""
        if schema is None:
            return None
        name = str(schema.get("title", "response")).lower()
        return {
            "type": "json_schema",
            "json_schema": {"name": name, "schema": schema, "strict": False},
        }

    # -- response conversion ------------------------------------------------

    def _parse_response(self, raw: Any) -> ModelResponse:
        choice = raw.choices[0] if raw.choices else None
        if choice is None:
            return ModelResponse(raw=raw)

        message: Any = choice.message or {}
        tool_calls = None
        if getattr(message, "tool_calls", None):
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments or "{}"),
                )
                for tc in message.tool_calls
            ]
        return ModelResponse(
            content=getattr(message, "content", "") or "",
            reasoning_content=_get_optional(message, "reasoning_content"),
            tool_calls=tool_calls,
            usage=self._parse_usage(raw.usage),
            raw=raw,
        )

    def _parse_usage(self, usage: Any) -> Usage | None:
        if usage is None:
            return None
        return Usage(
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            reasoning_tokens=_get_optional(
                getattr(usage, "completion_tokens_details", None), "reasoning_tokens"
            ),
        )

    def _parse_stream_chunk(self, chunk: Any) -> ModelResponse:
        """Parse one streaming chunk into a partial ModelResponse."""
        if not chunk.choices:
            return ModelResponse(raw=chunk)
        delta = chunk.choices[0].delta
        return ModelResponse(
            content=getattr(delta, "content", None) or "",
            reasoning_content=_get_optional(delta, "reasoning_content"),
            usage=self._parse_usage(chunk.usage),
            event="chunk",
            raw=chunk,
        )

    def _consume_chunk(self, chunk: Any, state: _StreamState) -> ModelResponse | None:
        """Update aggregation state from one chunk; return the partial event."""
        parsed = self._parse_stream_chunk(chunk)
        if parsed.content:
            state.content_parts.append(parsed.content)
        if parsed.reasoning_content:
            state.reasoning_parts.append(parsed.reasoning_content)
        if parsed.usage is not None:
            state.usage = parsed.usage

        delta = chunk.choices[0].delta if chunk.choices else None
        for tc in getattr(delta, "tool_calls", None) or []:
            acc = state.tool_calls_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            if tc.id:
                acc["id"] = tc.id
            if tc.function and tc.function.name:
                acc["name"] += tc.function.name
            if tc.function and tc.function.arguments:
                acc["arguments"] += tc.function.arguments

        if parsed.content or parsed.reasoning_content:
            return parsed
        return None

    def _build_complete(self, state: _StreamState) -> ModelResponse:
        tool_calls = None
        if state.tool_calls_acc:
            tool_calls = [
                ToolCall(
                    id=acc["id"],
                    name=acc["name"],
                    arguments=json.loads(acc["arguments"] or "{}"),
                )
                for acc in dict(sorted(state.tool_calls_acc.items())).values()
            ]
        return ModelResponse(
            content="".join(state.content_parts),
            reasoning_content="".join(state.reasoning_parts) or None,
            tool_calls=tool_calls,
            usage=state.usage,
            event="complete",
        )

    # -- sync API -----------------------------------------------------------

    def response(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        schema = self._normalize_schema(response_format) if response_format is not None else None
        prepared = self._prepare_messages(messages, schema)
        raw = self._get_client().chat.completions.create(
            model=self.id,
            messages=self._format_messages(prepared),
            tools=self._format_tools(tools),
            response_format=self._build_response_format(schema),
            **kwargs,
        )
        result = self._parse_response(raw)
        if schema is not None and response_format is not None and result.content:
            result.parsed = self._parse_structured(result.content, response_format)
        return result

    def response_stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> Iterator[ModelResponse]:
        schema = self._normalize_schema(response_format) if response_format is not None else None
        prepared = self._prepare_messages(messages, schema)
        stream = self._get_client().chat.completions.create(
            model=self.id,
            messages=self._format_messages(prepared),
            tools=self._format_tools(tools),
            response_format=self._build_response_format(schema),
            stream=True,
            **kwargs,
        )
        state = _StreamState()
        for chunk in stream:
            partial = self._consume_chunk(chunk, state)
            if partial is not None:
                yield partial
        final = self._build_complete(state)
        if schema is not None and response_format is not None and final.content:
            final.parsed = self._parse_structured(final.content, response_format)
        yield final

    # -- async API ----------------------------------------------------------

    async def aresponse(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        schema = self._normalize_schema(response_format) if response_format is not None else None
        prepared = self._prepare_messages(messages, schema)
        raw = await self._get_async_client().chat.completions.create(
            model=self.id,
            messages=self._format_messages(prepared),
            tools=self._format_tools(tools),
            response_format=self._build_response_format(schema),
            **kwargs,
        )
        result = self._parse_response(raw)
        if schema is not None and response_format is not None and result.content:
            result.parsed = self._parse_structured(result.content, response_format)
        return result

    async def aresponse_stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelResponse]:
        schema = self._normalize_schema(response_format) if response_format is not None else None
        prepared = self._prepare_messages(messages, schema)
        stream = await self._get_async_client().chat.completions.create(
            model=self.id,
            messages=self._format_messages(prepared),
            tools=self._format_tools(tools),
            response_format=self._build_response_format(schema),
            stream=True,
            **kwargs,
        )
        state = _StreamState()
        async for chunk in stream:
            partial = self._consume_chunk(chunk, state)
            if partial is not None:
                yield partial
        final = self._build_complete(state)
        if schema is not None and response_format is not None and final.content:
            final.parsed = self._parse_structured(final.content, response_format)
        yield final
