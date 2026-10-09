"""Model response structures returned by model adapters."""

from typing import Any

from pydantic import BaseModel, Field

from fakzed.model.message import ToolCall


class Usage(BaseModel):
    """Token usage for a single model call."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None


class ModelResponse(BaseModel):
    """Provider-agnostic model response.

    During streaming, one ModelResponse is yielded per event with `event` set
    to "content", "reasoning", or "complete". The final event ("complete")
    carries the aggregated content, tool calls, and usage.
    """

    content: str = ""
    reasoning_content: str | None = None
    tool_calls: list[ToolCall] | None = None
    usage: Usage | None = None
    event: str = "complete"
    parsed: Any = Field(default=None, exclude=True)
    raw: Any = Field(default=None, exclude=True)
