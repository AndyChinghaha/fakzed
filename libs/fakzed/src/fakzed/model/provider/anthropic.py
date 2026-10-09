"""Anthropic model adapter."""

import json
import os
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from fakzed.model.base import Model, ResponseFormat
from fakzed.model.message import Message, ToolCall
from fakzed.model.response import ModelResponse, Usage
from fakzed.model.tool import Tool


class AnthropicChat(Model):
    """Adapter for the Anthropic Messages API."""

    provider: str = "anthropic"
    base_url: str | None = None
    timeout: float | None = None
    max_retries: int = 2
    _client: Any = None
    _async_client: Any = None

    def get_api_key(self) -> str | None:
        return self.api_key or os.getenv("ANTHROPIC_API_KEY")

    def _get_client(self) -> Any:
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(
                api_key=self.get_api_key(),
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        return self._client

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            from anthropic import AsyncAnthropic

            self._async_client = AsyncAnthropic(
                api_key=self.get_api_key(),
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        return self._async_client

    # -- message conversion -------------------------------------------------

    def _format_message(self, message: Message) -> dict[str, Any]:
        """Convert one Message into one Anthropic wire message."""
        blocks: list[dict[str, Any]] = []

        if message.content and message.role != "tool":
            blocks.append({"type": "text", "text": message.content})

        if message.attachments:
            for attachment in message.attachments:
                source: dict[str, Any] = {
                    "type": "base64",
                    "media_type": attachment.media_type or "image/png",
                }
                if attachment.content:
                    source["data"] = attachment.content
                elif attachment.url:
                    source["data"] = attachment.url  # URL passthrough is provider-specific
                blocks.append({"type": "image", "source": source})

        if message.tool_calls:
            for tc in message.tool_calls:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    }
                )

        if message.tool_results:
            for result in message.tool_results:
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": result.tool_call_id,
                        "content": result.content,
                    }
                )

        role = message.role
        if role == "assistant" and not blocks:
            blocks.append({"type": "text", "text": ""})
        if role == "tool":
            # tool results are attached to user messages in Anthropic's format
            role = "user"
        return {"role": role, "content": blocks}

    def _format_messages(self, messages: Sequence[Message]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        wire_messages: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue
            wire_messages.append(self._format_message(message))
        return "\n".join(system_parts), wire_messages

    def _format_tools(self, tools: Sequence[Tool] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    # -- response conversion ------------------------------------------------

    def _parse_response(self, raw: Any) -> ModelResponse:
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in raw.content or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(block.text)
            elif block_type == "thinking":
                reasoning_parts.append(block.thinking)
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {}))
                )

        usage = None
        if raw.usage is not None:
            usage = Usage(
                input_tokens=getattr(raw.usage, "input_tokens", None),
                output_tokens=getattr(raw.usage, "output_tokens", None),
                total_tokens=(
                    (getattr(raw.usage, "input_tokens", 0) or 0)
                    + (getattr(raw.usage, "output_tokens", 0) or 0)
                    or None
                ),
            )
        return ModelResponse(
            content="".join(text_parts),
            reasoning_content="".join(reasoning_parts) or None,
            tool_calls=tool_calls or None,
            usage=usage,
            raw=raw,
        )

    def _parse_stream_chunk(self, event: Any) -> ModelResponse:
        event_type = getattr(event, "type", None)
        if event_type == "content_block_delta":
            delta = event.delta
            if getattr(delta, "type", None) == "text_delta":
                return ModelResponse(content=delta.text, event="chunk", raw=event)
            if getattr(delta, "type", None) == "thinking_delta":
                return ModelResponse(reasoning_content=delta.thinking, event="chunk", raw=event)
        if event_type == "content_block_stop":
            return ModelResponse(event="chunk", raw=event)
        return ModelResponse(raw=event)

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
        system, wire_messages = self._format_messages(prepared)
        raw = self._get_client().messages.create(
            model=self.id,
            system=system or None,
            messages=wire_messages,
            tools=self._format_tools(tools),
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
        system, wire_messages = self._format_messages(prepared)
        stream = self._get_client().messages.stream(
            model=self.id,
            system=system or None,
            messages=wire_messages,
            tools=self._format_tools(tools),
            **kwargs,
        )
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None

        with stream as s:
            for event in s:
                parsed = self._parse_stream_chunk(event)
                if parsed.content:
                    text_parts.append(parsed.content)
                    yield parsed
                if parsed.reasoning_content:
                    reasoning_parts.append(parsed.reasoning_content)
                    yield parsed
                if getattr(event, "type", None) == "content_block_start":
                    block = event.content_block
                    if getattr(block, "type", None) == "tool_use":
                        tool_calls_acc[block.index] = {
                            "id": block.id,
                            "name": block.name,
                            "arguments": "",
                        }
                if getattr(event, "type", None) == "content_block_delta":
                    delta = event.delta
                    if getattr(delta, "type", None) == "input_json_delta":
                        acc = tool_calls_acc.setdefault(
                            event.index, {"id": "", "name": "", "arguments": ""}
                        )
                        acc["arguments"] += delta.partial_json
                if getattr(event, "type", None) == "message_delta" and event.usage is not None:
                    usage = Usage(
                        input_tokens=getattr(event.usage, "input_tokens", None),
                        output_tokens=getattr(event.usage, "output_tokens", None),
                    )

        tool_calls = None
        if tool_calls_acc:
            tool_calls = [
                ToolCall(
                    id=acc["id"],
                    name=acc["name"],
                    arguments=json.loads(acc["arguments"] or "{}"),
                )
                for acc in dict(sorted(tool_calls_acc.items())).values()
            ]
        final = ModelResponse(
            content="".join(text_parts),
            reasoning_content="".join(reasoning_parts) or None,
            tool_calls=tool_calls,
            usage=usage,
            event="complete",
        )
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
        system, wire_messages = self._format_messages(prepared)
        raw = await self._get_async_client().messages.create(
            model=self.id,
            system=system or None,
            messages=wire_messages,
            tools=self._format_tools(tools),
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
        system, wire_messages = self._format_messages(prepared)
        stream = self._get_async_client().messages.stream(
            model=self.id,
            system=system or None,
            messages=wire_messages,
            tools=self._format_tools(tools),
            **kwargs,
        )
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None

        async with stream as s:
            async for event in s:
                parsed = self._parse_stream_chunk(event)
                if parsed.content:
                    text_parts.append(parsed.content)
                    yield parsed
                if parsed.reasoning_content:
                    reasoning_parts.append(parsed.reasoning_content)
                    yield parsed
                if getattr(event, "type", None) == "content_block_start":
                    block = event.content_block
                    if getattr(block, "type", None) == "tool_use":
                        tool_calls_acc[block.index] = {
                            "id": block.id,
                            "name": block.name,
                            "arguments": "",
                        }
                if getattr(event, "type", None) == "content_block_delta":
                    delta = event.delta
                    if getattr(delta, "type", None) == "input_json_delta":
                        acc = tool_calls_acc.setdefault(
                            event.index, {"id": "", "name": "", "arguments": ""}
                        )
                        acc["arguments"] += delta.partial_json
                if getattr(event, "type", None) == "message_delta" and event.usage is not None:
                    usage = Usage(
                        input_tokens=getattr(event.usage, "input_tokens", None),
                        output_tokens=getattr(event.usage, "output_tokens", None),
                    )

        tool_calls = None
        if tool_calls_acc:
            tool_calls = [
                ToolCall(
                    id=acc["id"],
                    name=acc["name"],
                    arguments=json.loads(acc["arguments"] or "{}"),
                )
                for acc in dict(sorted(tool_calls_acc.items())).values()
            ]
        final = ModelResponse(
            content="".join(text_parts),
            reasoning_content="".join(reasoning_parts) or None,
            tool_calls=tool_calls,
            usage=usage,
            event="complete",
        )
        if schema is not None and response_format is not None and final.content:
            final.parsed = self._parse_structured(final.content, response_format)
        yield final
