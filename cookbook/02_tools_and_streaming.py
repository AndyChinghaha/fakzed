"""Cookbook 02: tools — the model calls a function, the loop runs it, the
model continues until it produces a final answer.

Run:  python cookbook/02_tools_and_streaming.py
"""

from _cookbook_utils import ScriptedModel

from fakzed import Agent, tool
from fakzed.model import ModelResponse, ToolCall


@tool
def calculator(expression: str) -> str:
    """Evaluate a math expression. Supports + - * / and parentheses."""
    # A tiny whitelist evaluator — AST-whitelisted for safety in production.
    return str(eval(expression, {"__builtins__": {}}, {}))


# Script the model: first reply is a tool call, second is the final answer.
model = ScriptedModel(
    responses=[
        ModelResponse(
            content="",
            tool_calls=[
                ToolCall(id="c1", name="calculator", arguments={"expression": "12 + 30 * 2"})
            ],
        ),
        ModelResponse(content="(12 + 30) × 2 的结果是 72。"),
    ]
)

agent = Agent(
    name="math-bot",
    model=model,
    instructions="你是数学助手，会使用 calculator 工具。",
    tools=[calculator],
)

resp = agent.run("帮我算 (12 + 30) * 2")
print("最终答案:", resp.content)
tool_msgs = [m for m in resp.messages if m.role == "tool"]
print("工具执行次数:", len(tool_msgs))
print("消息条数:", len(resp.messages))
