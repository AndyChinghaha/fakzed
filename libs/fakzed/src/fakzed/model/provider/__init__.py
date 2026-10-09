"""Model provider adapters.

Importing this package registers every adapter with the model factory.
"""

from fakzed.model.provider.anthropic import AnthropicChat
from fakzed.model.provider.deepseek import DeepSeekChat
from fakzed.model.provider.ollama import OllamaChat
from fakzed.model.provider.openai import OpenAIChat
from fakzed.model.registry import register_model

register_model("openai")(OpenAIChat)
register_model("deepseek")(DeepSeekChat)
register_model("anthropic")(AnthropicChat)
register_model("ollama")(OllamaChat)

__all__ = ["OpenAIChat", "DeepSeekChat", "AnthropicChat", "OllamaChat"]
