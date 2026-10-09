"""Tests for Anthropic message conversion (no network calls)."""

from fakzed.model import Message, Tool, ToolCall, ToolResult
from fakzed.model.provider import AnthropicChat


def make_model() -> AnthropicChat:
    return AnthropicChat(id="claude-sonnet-4-5", api_key="test-key")


def test_format_messages_splits_system() -> None:
    model = make_model()
    system, wire = model._format_messages(  # noqa: SLF001
        [
            Message(role="system", content="Be brief."),
            Message(role="user", content="Hi"),
        ]
    )
    assert system == "Be brief."
    assert wire == [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}]


def test_format_tool_calls() -> None:
    model = make_model()
    _, wire = model._format_messages(  # noqa: SLF001
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
    assert wire[0]["content"] == [
        {"type": "tool_use", "id": "call_1", "name": "get_weather", "input": {"city": "Beijing"}}
    ]


def test_format_tool_results_as_user() -> None:
    model = make_model()
    _, wire = model._format_messages(  # noqa: SLF001
        [
            Message(
                role="tool",
                content="25C",
                tool_results=[ToolResult(tool_call_id="call_1", content="25C")],
            )
        ]
    )
    assert wire[0]["role"] == "user"
    assert wire[0]["content"] == [
        {"type": "tool_result", "tool_use_id": "call_1", "content": "25C"}
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
            "name": "get_weather",
            "description": "Get weather",
            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
        }
    ]


def test_parse_response_with_tool_use() -> None:
    model = make_model()

    class FakeTextBlock:
        type = "text"
        text = "Sure, checking."

    class FakeToolUseBlock:
        type = "tool_use"
        id = "toolu_1"
        name = "get_weather"
        input = {"city": "Beijing"}

    class FakeUsage:
        input_tokens = 10
        output_tokens = 20

    class FakeRaw:
        content = [FakeTextBlock(), FakeToolUseBlock()]
        usage = FakeUsage()

    response = model._parse_response(FakeRaw())  # noqa: SLF001
    assert response.content == "Sure, checking."
    assert response.tool_calls == [
        ToolCall(id="toolu_1", name="get_weather", arguments={"city": "Beijing"})
    ]
    assert response.usage is not None
    assert response.usage.input_tokens == 10


def test_parse_response_with_thinking() -> None:
    model = make_model()

    class FakeThinkingBlock:
        type = "thinking"
        thinking = "Hmm..."

    class FakeRaw:
        content = [FakeThinkingBlock()]
        usage = None

    response = model._parse_response(FakeRaw())  # noqa: SLF001
    assert response.reasoning_content == "Hmm..."
    assert response.content == ""
