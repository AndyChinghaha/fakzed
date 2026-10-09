"""DeepSeek model adapter.

DeepSeek exposes an OpenAI-compatible API; reasoning models (deepseek-reasoner)
return chain-of-thought in `reasoning_content`, which the OpenAIChat base
already surfaces as `ModelResponse.reasoning_content`.

For structured output, DeepSeek uses `json_object` mode with the JSON schema
injected into the prompt (the base class handles the injection).
"""

import os
from typing import Any

from fakzed.model.provider.openai import OpenAIChat


class DeepSeekChat(OpenAIChat):
    """Adapter for the DeepSeek API (https://api.deepseek.com)."""

    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"

    def get_api_key(self) -> str | None:
        return self.api_key or os.getenv("DEEPSEEK_API_KEY")

    def _supports_native_json_schema(self) -> bool:
        return False

    def _build_response_format(self, schema: dict[str, Any] | None) -> dict[str, Any] | None:
        """DeepSeek json_object mode; schema is injected into the prompt."""
        if schema is None:
            return None
        return {"type": "json_object"}
