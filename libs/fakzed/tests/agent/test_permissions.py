"""Permission tests: dangerous tools are gated by the agent's policy callback."""

from conftest import FakeModel

from fakzed import Agent
from fakzed.model import ModelResponse, ToolCall
from fakzed.tools import tool


@tool(dangerous=True)
def delete_all(target: str) -> str:
    """Delete everything (dangerous)."""
    return f"deleted {target}"


def test_no_handler_allows_dangerous_tools():
    model = FakeModel(responses=[ModelResponse(content="done")])
    agent = Agent(model=model, tools=[delete_all])
    result = agent._execute_tool(ToolCall(id="c1", name="delete_all", arguments={"target": "db"}))  # noqa: SLF001
    assert result == "deleted db"


def test_handler_denies_dangerous_tools():
    model = FakeModel()
    model.enqueue(
        ModelResponse(
            tool_calls=[ToolCall(id="c1", name="delete_all", arguments={"target": "db"})]
        ),
        ModelResponse(content="ok, the delete was blocked"),
    )
    agent = Agent(
        model=model,
        tools=[delete_all],
        tool_permission_handler=lambda tool, args: tool.name == "safe_tool",
    )
    agent.run("delete the db")

    # the model's second call saw the rejection message
    tool_message = model.calls[-1]["messages"][-1]
    assert tool_message.role == "tool"
    assert "rejected by the permission policy" in tool_message.content


def test_handler_allows_approved_tools():
    model = FakeModel()
    model.enqueue(
        ModelResponse(
            tool_calls=[ToolCall(id="c1", name="delete_all", arguments={"target": "tmp"})]
        ),
        ModelResponse(content="approved and ran"),
    )
    agent = Agent(
        model=model,
        tools=[delete_all],
        tool_permission_handler=lambda tool, args: True,
    )
    agent.run("clean tmp")
    tool_message = model.calls[-1]["messages"][-1]
    assert tool_message.content == "deleted tmp"


def test_handler_exception_denies_by_default():
    def broken_policy(tool, args):
        raise RuntimeError("policy crashed")

    model = FakeModel()
    model.enqueue(
        ModelResponse(tool_calls=[ToolCall(id="c1", name="delete_all", arguments={})]),
        ModelResponse(content="fallback"),
    )
    agent = Agent(model=model, tools=[delete_all], tool_permission_handler=broken_policy)
    agent.run("anything")
    tool_message = model.calls[-1]["messages"][-1]
    assert "rejected by the permission policy" in tool_message.content
