"""Message data structures shared across all model providers."""

from typing import Any, Literal

from pydantic import BaseModel, Field

MessageRole = Literal["system", "user", "assistant", "tool", "developer"]


class Attachment(BaseModel):
    """An attachment attached to a message (image, audio, video, or file)."""

    url: str | None = None
    content: str | None = None
    filename: str | None = None
    media_type: str | None = None


class ToolCall(BaseModel):
    """A tool call emitted by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """The result of executing a tool call, sent back to the model."""

    tool_call_id: str
    content: str


class Message(BaseModel):
    """A single chat message.

    Provider-agnostic; each model adapter converts to/from its native format.
    """

    role: MessageRole
    content: str = ""
    name: str | None = None
    attachments: list[Attachment] | None = None
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None
    reasoning_content: str | None = None

    def get_content(self) -> str:
        return self.content or ""
