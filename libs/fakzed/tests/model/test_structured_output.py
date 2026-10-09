"""Tests for structured output across providers (no network calls)."""

from pydantic import BaseModel

from fakzed.model import Message
from fakzed.model.base import _extract_json
from fakzed.model.provider import AnthropicChat, DeepSeekChat, OllamaChat, OpenAIChat


class CityWeather(BaseModel):
    city: str
    temperature: float


def test_extract_json_plain() -> None:
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_json_markdown_fence() -> None:
    content = '```json\n{"a": 1}\n```'
    assert _extract_json(content) == '{"a": 1}'


def test_normalize_schema_from_pydantic() -> None:
    model = OpenAIChat(id="gpt-4o")
    schema = model._normalize_schema(CityWeather)  # noqa: SLF001
    assert schema["type"] == "object"
    assert "city" in schema["properties"]


def test_normalize_schema_from_dict() -> None:
    model = OpenAIChat(id="gpt-4o")
    raw = {"type": "object", "properties": {"x": {"type": "integer"}}}
    assert model._normalize_schema(raw) is raw  # noqa: SLF001


def test_openai_build_response_format() -> None:
    model = OpenAIChat(id="gpt-4o")
    schema = {"title": "CityWeather", "type": "object"}
    rf = model._build_response_format(schema)  # noqa: SLF001
    assert rf == {
        "type": "json_schema",
        "json_schema": {"name": "cityweather", "schema": schema, "strict": False},
    }


def test_deepseek_uses_json_object_with_injection() -> None:
    model = DeepSeekChat(id="deepseek-chat")
    schema = {"type": "object"}
    assert model._supports_native_json_schema() is False  # noqa: SLF001
    assert model._build_response_format(schema) == {"type": "json_object"}  # noqa: SLF001

    messages = [Message(role="user", content="weather in Beijing?")]
    prepared = model._prepare_messages(messages, schema)  # noqa: SLF001
    assert len(prepared) == 2
    assert prepared[-1].role == "system"
    assert '"type": "object"' in prepared[-1].content


def test_anthropic_injects_schema() -> None:
    model = AnthropicChat(id="claude-sonnet-4-5")
    assert model._supports_native_json_schema() is False  # noqa: SLF001
    assert model._build_response_format({"type": "object"}) is None  # noqa: SLF001

    messages = [Message(role="user", content="hi")]
    prepared = model._prepare_messages(messages, {"type": "object"})  # noqa: SLF001
    assert len(prepared) == 2
    assert prepared[-1].role == "system"


def test_ollama_native_schema() -> None:
    model = OllamaChat(id="llama3.2")
    assert model._supports_native_json_schema() is True  # noqa: SLF001
    schema = {"type": "object"}
    assert model._build_response_format(schema) is schema  # noqa: SLF001
    # native support means no prompt injection
    prepared = model._prepare_messages([Message(role="user", content="hi")], schema)  # noqa: SLF001
    assert len(prepared) == 1


def test_parse_structured_pydantic() -> None:
    model = OpenAIChat(id="gpt-4o")
    parsed = model._parse_structured('{"city": "Beijing", "temperature": 25.5}', CityWeather)  # noqa: SLF001
    assert isinstance(parsed, CityWeather)
    assert parsed.city == "Beijing"
    assert parsed.temperature == 25.5


def test_parse_structured_dict() -> None:
    model = OpenAIChat(id="gpt-4o")
    parsed = model._parse_structured('```json\n{"x": 1}\n```', {"type": "object"})  # noqa: SLF001
    assert parsed == {"x": 1}


def test_no_injection_without_format() -> None:
    model = DeepSeekChat(id="deepseek-chat")
    messages = [Message(role="user", content="hi")]
    prepared = model._prepare_messages(messages, None)  # noqa: SLF001
    assert prepared is not messages
    assert len(prepared) == 1
