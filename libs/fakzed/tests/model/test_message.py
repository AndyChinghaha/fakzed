"""Tests for message data structures."""

from fakzed.model import Attachment, Message, ToolCall, ToolResult


def test_message_roundtrip() -> None:
    message = Message(role="user", content="hello")
    data = message.model_dump()
    restored = Message.model_validate(data)
    assert restored == message


def test_message_json_roundtrip() -> None:
    message = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="call_1", name="get_weather", arguments={"city": "Beijing"})],
    )
    restored = Message.model_validate_json(message.model_dump_json())
    assert restored.tool_calls == [
        ToolCall(id="call_1", name="get_weather", arguments={"city": "Beijing"})
    ]


def test_tool_result() -> None:
    result = ToolResult(tool_call_id="call_1", content="25C")
    message = Message(role="tool", content=result.content, tool_results=[result])
    assert message.tool_results[0].tool_call_id == "call_1"


def test_attachment() -> None:
    message = Message(
        role="user",
        content="What is this?",
        attachments=[Attachment(url="https://example.com/img.png", media_type="image/png")],
    )
    assert message.attachments[0].url == "https://example.com/img.png"


def test_reasoning_content() -> None:
    message = Message(role="assistant", content="answer", reasoning_content="step by step...")
    assert message.reasoning_content == "step by step..."


def test_get_content() -> None:
    assert Message(role="user").get_content() == ""
    assert Message(role="user", content="hi").get_content() == "hi"
