"""Model provider registry: maps provider names to Model adapter classes."""

from collections.abc import Callable

from fakzed.model.base import Model

_MODEL_REGISTRY: dict[str, type[Model]] = {}


def register_model(provider: str) -> Callable[[type[Model]], type[Model]]:
    """Class decorator that registers a Model adapter under a provider name."""

    def decorator(cls: type[Model]) -> type[Model]:
        _MODEL_REGISTRY[provider] = cls
        return cls

    return decorator


def get_model_class(provider: str) -> type[Model] | None:
    return _MODEL_REGISTRY.get(provider)


def registered_providers() -> list[str]:
    return sorted(_MODEL_REGISTRY)
