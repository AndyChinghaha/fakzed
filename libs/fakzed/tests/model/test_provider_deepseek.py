"""Tests for the DeepSeek adapter (no network calls)."""

from fakzed.model import create_model
from fakzed.model.provider import DeepSeekChat


def test_deepseek_defaults() -> None:
    model = DeepSeekChat(id="deepseek-chat")
    assert model.provider == "deepseek"
    assert model.base_url == "https://api.deepseek.com"


def test_api_key_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    model = DeepSeekChat(id="deepseek-chat")
    assert model.get_api_key() == "env-key"


def test_api_key_prefers_explicit(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    model = DeepSeekChat(id="deepseek-chat", api_key="explicit-key")
    assert model.get_api_key() == "explicit-key"


def test_create_via_factory() -> None:
    model = create_model("deepseek:deepseek-reasoner")
    assert isinstance(model, DeepSeekChat)
    assert model.id == "deepseek-reasoner"


def test_reasoning_content_in_response() -> None:
    """DeepSeek reasoning models surface `reasoning_content` on the response."""
    model = DeepSeekChat(id="deepseek-reasoner")

    class FakeMessage:
        content = "The answer is 42."
        reasoning_content = "Let me think..."

    class FakeRaw:
        choices = [type("C", (), {"message": FakeMessage()})()]
        usage = None

    response = model._parse_response(FakeRaw())  # noqa: SLF001
    assert response.content == "The answer is 42."
    assert response.reasoning_content == "Let me think..."


def test_reasoning_content_in_stream_chunk() -> None:
    model = DeepSeekChat(id="deepseek-reasoner")

    class FakeDelta:
        content = None
        reasoning_content = "thinking..."

    class FakeChunk:
        choices = [type("C", (), {"delta": FakeDelta()})()]
        usage = None

    parsed = model._parse_stream_chunk(FakeChunk())  # noqa: SLF001
    assert parsed.reasoning_content == "thinking..."
    assert parsed.content == ""


def test_usage_with_reasoning_tokens() -> None:
    model = DeepSeekChat(id="deepseek-reasoner")

    class FakeUsage:
        prompt_tokens = 10
        completion_tokens = 20
        total_tokens = 30
        completion_tokens_details = type("D", (), {"reasoning_tokens": 15})()

    usage = model._parse_usage(FakeUsage())  # noqa: SLF001
    assert usage is not None
    assert usage.input_tokens == 10
    assert usage.output_tokens == 20
    assert usage.reasoning_tokens == 15
