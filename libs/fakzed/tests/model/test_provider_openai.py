"""Tests for OpenAI message conversion (no network calls)."""

from fakzed.model import Message, Tool, ToolCall, ToolResult
from fakzed.model.provider import OpenAIChat


def make_model() -> OpenAIChat:
    return OpenAIChat(id="gpt-4o", api_key="test-key")


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


def test_format_tool_call_message() -> None:
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
            "function": {"name": "get_weather", "arguments": '{"city": "Beijing"}'},
        }
    ]


def test_format_tool_result_splits_messages() -> None:
    model = make_model()
    wire = model._format_messages(  # noqa: SLF001
        [
            Message(
                role="tool",
                content="25C",
                tool_results=[ToolResult(tool_call_id="call_1", content="25C")],
            )
        ]
    )
    assert wire == [{"role": "tool", "tool_call_id": "call_1", "content": "25C"}]


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


def test_format_tools_empty() -> None:
    model = make_model()
    assert model._format_tools([]) is None  # noqa: SLF001
    assert model._format_tools(None) is None  # noqa: SLF001


def test_format_attachment_url() -> None:
    from fakzed.model import Attachment

    model = make_model()
    wire = model._format_messages(  # noqa: SLF001
        [
            Message(
                role="user", content="What is this?", attachments=[Attachment(url="http://x/i.png")]
            )
        ]
    )
    assert wire[0]["content"] == [
        {"type": "text", "text": "What is this?"},
        {"type": "image_url", "image_url": {"url": "http://x/i.png"}},
    ]


def test_api_key_fallback_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    model = OpenAIChat(id="gpt-4o")
    assert model.get_api_key() == "env-key"

    model_with_key = OpenAIChat(id="gpt-4o", api_key="explicit-key")
    assert model_with_key.get_api_key() == "explicit-key"
