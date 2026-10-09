"""Tests for Ollama message conversion (no network calls)."""

from fakzed.model import Message, Tool, ToolCall
from fakzed.model.provider import OllamaChat


def make_model() -> OllamaChat:
    return OllamaChat(id="llama3.2")


def test_format_simple_messages() -> None:
    model = make_model()
    wire = model._format_messages(  # noqa: SLF001
        [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hi"),
        ]
    )
    assert wire == [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
    ]


def test_format_tool_calls() -> None:
    model = make_model()
    wire = model._format_messages(  # noqa: SLF001
        [
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(id="call_1", name="get_weather", arguments={"city": "Beijing"})
                ],
            )
        ]
    )
    assert wire[0]["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_weather", "arguments": {"city": "Beijing"}},
        }
    ]


def test_format_tools() -> None:
    model = make_model()
    tool = Tool(
        name="get_weather",
        description="Get weather",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
    )
    wire = model._format_tools([tool])  # noqa: SLF001
    assert wire == [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
        }
    ]


def test_parse_response() -> None:
    model = make_model()

    class FakeMessage:
        content = "Hello!"
        thinking = None
        tool_calls = None

    class FakeRaw:
        message = FakeMessage()
        prompt_eval_count = 5
        eval_count = 7

    response = model._parse_response(FakeRaw())  # noqa: SLF001
    assert response.content == "Hello!"
    assert response.usage is not None
    assert response.usage.input_tokens == 5
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 12
