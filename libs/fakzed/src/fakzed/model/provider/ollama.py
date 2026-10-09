"""Ollama model adapter (local models via the Ollama API)."""

import json
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from fakzed.model.base import Model, ResponseFormat
from fakzed.model.message import Message, ToolCall
from fakzed.model.response import ModelResponse, Usage
from fakzed.model.tool import Tool


class OllamaChat(Model):
    """Adapter for the Ollama API (https://ollama.com)."""

    provider: str = "ollama"
    host: str | None = None
    timeout: float | None = None
    keep_alive: str | float | None = None
    _client: Any = None
    _async_client: Any = None

    def get_api_key(self) -> str | None:
        return self.api_key

    def _get_client(self) -> Any:
        if self._client is None:
            import ollama

            kwargs: dict[str, Any] = {}
            if self.host:
                kwargs["host"] = self.host
            if self.timeout:
                kwargs["timeout"] = self.timeout
            self._client = ollama.Client(**kwargs)
        return self._client

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            import ollama

            kwargs: dict[str, Any] = {}
            if self.host:
                kwargs["host"] = self.host
            if self.timeout:
                kwargs["timeout"] = self.timeout
            self._async_client = ollama.AsyncClient(**kwargs)
        return self._async_client

    # -- message conversion -------------------------------------------------

    def _format_message(self, message: Message) -> dict[str, Any]:
        wire: dict[str, Any] = {"role": message.role, "content": message.content or ""}
        if message.attachments:
            images: list[str] = []
            for attachment in message.attachments:
                if attachment.url:
                    images.append(attachment.url)
                elif attachment.content:
                    images.append(attachment.content)
            if images:
                wire["images"] = images
        if message.tool_calls:
            wire["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in message.tool_calls
            ]
        if message.tool_results:
            for result in message.tool_results:
                wire["tool_call_id"] = result.tool_call_id
                wire["content"] = result.content
        return wire

    def _format_messages(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        return [self._format_message(message) for message in messages]

    def _format_tools(self, tools: Sequence[Tool] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    # -- structured output ---------------------------------------------------

    def _supports_native_json_schema(self) -> bool:
        return True

    def _build_response_format(self, schema: dict[str, Any] | None) -> dict[str, Any] | None:
        """Ollama's `format` parameter accepts a raw JSON schema."""
        return schema

    # -- response conversion ------------------------------------------------

    def _parse_response(self, raw: Any) -> ModelResponse:
        message: Any = getattr(raw, "message", None) or {}
        tool_calls = None
        if getattr(message, "tool_calls", None):
            tool_calls = [
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or {})
                for tc in message.tool_calls
            ]
        usage = None
        if getattr(raw, "prompt_eval_count", None) is not None:
            usage = Usage(
                input_tokens=raw.prompt_eval_count,
                output_tokens=raw.eval_count,
                total_tokens=(raw.prompt_eval_count or 0) + (raw.eval_count or 0),
            )
        return ModelResponse(
            content=getattr(message, "content", "") or "",
            reasoning_content=getattr(message, "thinking", None),
            tool_calls=tool_calls,
            usage=usage,
            raw=raw,
        )

    def _parse_stream_chunk(self, chunk: Any) -> ModelResponse:
        message = getattr(chunk, "message", None) or {}
        usage = None
        if getattr(chunk, "prompt_eval_count", None) is not None:
            usage = Usage(
                input_tokens=chunk.prompt_eval_count,
                output_tokens=chunk.eval_count,
                total_tokens=(chunk.prompt_eval_count or 0) + (chunk.eval_count or 0),
            )
        return ModelResponse(
            content=getattr(message, "content", "") or "",
            reasoning_content=getattr(message, "thinking", None),
            usage=usage,
            event="chunk",
            raw=chunk,
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
        raw = self._get_client().chat(
            model=self.id,
            messages=self._format_messages(prepared),
            tools=self._format_tools(tools),
            format=self._build_response_format(schema),
            keep_alive=self.keep_alive,
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
        stream = self._get_client().chat(
            model=self.id,
            messages=self._format_messages(prepared),
            tools=self._format_tools(tools),
            format=self._build_response_format(schema),
            keep_alive=self.keep_alive,
            stream=True,
            **kwargs,
        )
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None

        for chunk in stream:
            parsed = self._parse_stream_chunk(chunk)
            if parsed.content:
                content_parts.append(parsed.content)
            if parsed.reasoning_content:
                reasoning_parts.append(parsed.reasoning_content)
            if parsed.usage is not None:
                usage = parsed.usage

            message: Any = getattr(chunk, "message", None) or {}
            for tc in getattr(message, "tool_calls", None) or []:
                index = getattr(tc, "index", 0)
                acc = tool_calls_acc.setdefault(
                    index,
                    {"id": tc.id or "", "name": "", "arguments": {}},
                )
                function = getattr(tc, "function", None)
                if function is not None:
                    if function.name:
                        acc["name"] += function.name
                    if function.arguments:
                        try:
                            acc["arguments"].update(json.loads(function.arguments))
                        except json.JSONDecodeError:
                            acc["arguments"] = {"raw": function.arguments}

            if parsed.content or parsed.reasoning_content:
                yield parsed

        tool_calls = None
        if tool_calls_acc:
            tool_calls = [
                ToolCall(id=acc["id"], name=acc["name"], arguments=acc["arguments"])
                for acc in dict(sorted(tool_calls_acc.items())).values()
            ]
        final = ModelResponse(
            content="".join(content_parts),
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
        raw = await self._get_async_client().chat(
            model=self.id,
            messages=self._format_messages(prepared),
            tools=self._format_tools(tools),
            format=self._build_response_format(schema),
            keep_alive=self.keep_alive,
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
        stream = await self._get_async_client().chat(
            model=self.id,
            messages=self._format_messages(prepared),
            tools=self._format_tools(tools),
            format=self._build_response_format(schema),
            keep_alive=self.keep_alive,
            stream=True,
            **kwargs,
        )
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None

        async for chunk in stream:
            parsed = self._parse_stream_chunk(chunk)
            if parsed.content:
                content_parts.append(parsed.content)
            if parsed.reasoning_content:
                reasoning_parts.append(parsed.reasoning_content)
            if parsed.usage is not None:
                usage = parsed.usage

            message: Any = getattr(chunk, "message", None) or {}
            for tc in getattr(message, "tool_calls", None) or []:
                index = getattr(tc, "index", 0)
                acc = tool_calls_acc.setdefault(
                    index,
                    {"id": tc.id or "", "name": "", "arguments": {}},
                )
                function = getattr(tc, "function", None)
                if function is not None:
                    if function.name:
                        acc["name"] += function.name
                    if function.arguments:
                        try:
                            acc["arguments"].update(json.loads(function.arguments))
                        except json.JSONDecodeError:
                            acc["arguments"] = {"raw": function.arguments}

            if parsed.content or parsed.reasoning_content:
                yield parsed

        tool_calls = None
        if tool_calls_acc:
            tool_calls = [
                ToolCall(id=acc["id"], name=acc["name"], arguments=acc["arguments"])
                for acc in dict(sorted(tool_calls_acc.items())).values()
            ]
        final = ModelResponse(
            content="".join(content_parts),
            reasoning_content="".join(reasoning_parts) or None,
            tool_calls=tool_calls,
            usage=usage,
            event="complete",
        )
        if schema is not None and response_format is not None and final.content:
            final.parsed = self._parse_structured(final.content, response_format)
        yield final
