"""Model factory: turn "provider:model" into a Model instance."""

from typing import Any

from fakzed.model.base import Model
from fakzed.model.registry import get_model_class, registered_providers


def parse_model_id(model_id: str) -> tuple[str, str]:
    """Split "provider:model-name" into (provider, model-name)."""
    if ":" not in model_id:
        raise ValueError(f"Invalid model id '{model_id}'. Expected format 'provider:model-name'.")
    provider, _, name = model_id.partition(":")
    if not provider or not name:
        raise ValueError(f"Invalid model id '{model_id}'. Expected format 'provider:model-name'.")
    return provider, name


def create_model(model: Model | str, **kwargs: Any) -> Model:
    """Create a Model from an instance or a "provider:model-name" string."""
    if isinstance(model, Model):
        return model
    if not isinstance(model, str):
        raise TypeError(f"Expected Model or str, got {type(model).__name__}")

    provider, model_name = parse_model_id(model)
    cls = get_model_class(provider)
    if cls is None:
        known = ", ".join(registered_providers()) or "none"
        raise ValueError(f"Unknown model provider '{provider}'. Known providers: {known}")

    return cls(id=model_name, **kwargs)


# Import provider modules to trigger registration.
from fakzed.model.provider import anthropic, deepseek, ollama, openai  # noqa: E402,F401

__all__ = ["parse_model_id", "create_model"]
