"""Model abstraction layer.

Unified interface over LLM providers, standardized tool calling,
structured output, and streaming.

Usage:
    from fakzed.model import create_model, Message

    model = create_model("deepseek:deepseek-chat")
    response = model.response(messages=[Message(role="user", content="Hi")])
"""

from fakzed.model.base import Model
from fakzed.model.factory import create_model, parse_model_id
from fakzed.model.message import Attachment, Message, MessageRole, ToolCall, ToolResult
from fakzed.model.pricing import MODEL_PRICING, estimate_cost, find_price, merge_usage
from fakzed.model.registry import get_model_class, register_model, registered_providers
from fakzed.model.response import ModelResponse, Usage
from fakzed.model.tool import Tool

__all__ = [
    "Model",
    "create_model",
    "parse_model_id",
    "get_model_class",
    "register_model",
    "registered_providers",
    "Message",
    "MessageRole",
    "Attachment",
    "ToolCall",
    "ToolResult",
    "ModelResponse",
    "Usage",
    "Tool",
    "MODEL_PRICING",
    "estimate_cost",
    "find_price",
    "merge_usage",
]
