"""Tests for the model factory and registry."""

import pytest

from fakzed.model import Model, create_model, parse_model_id, registered_providers
from fakzed.model.provider import AnthropicChat, DeepSeekChat, OllamaChat, OpenAIChat


def test_parse_model_id() -> None:
    assert parse_model_id("openai:gpt-4o") == ("openai", "gpt-4o")
    assert parse_model_id("deepseek:deepseek-chat") == ("deepseek", "deepseek-chat")


def test_parse_model_id_invalid() -> None:
    with pytest.raises(ValueError):
        parse_model_id("no-colon")
    with pytest.raises(ValueError):
        parse_model_id(":missing-name")
    with pytest.raises(ValueError):
        parse_model_id("provider:")


def test_providers_registered() -> None:
    providers = registered_providers()
    assert {"openai", "deepseek", "anthropic", "ollama"} <= set(providers)


def test_create_model_by_id() -> None:
    model = create_model("openai:gpt-4o")
    assert isinstance(model, OpenAIChat)
    assert model.id == "gpt-4o"

    ds = create_model("deepseek:deepseek-chat")
    assert isinstance(ds, DeepSeekChat)
    assert ds.id == "deepseek-chat"
    assert ds.base_url == "https://api.deepseek.com"

    assert isinstance(create_model("anthropic:claude-sonnet-4-5"), AnthropicChat)
    assert isinstance(create_model("ollama:llama3.2"), OllamaChat)


def test_create_model_passthrough() -> None:
    model = OpenAIChat(id="gpt-4o")
    assert create_model(model) is model


def test_create_model_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown model provider"):
        create_model("unknown:model")


def test_create_model_invalid_type() -> None:
    with pytest.raises(TypeError):
        create_model(42)  # type: ignore[arg-type]


def test_model_is_pydantic() -> None:
    model: Model = create_model("openai:gpt-4o")
    dumped = model.model_dump()
    assert dumped["id"] == "gpt-4o"
    assert dumped["provider"] == "openai"
