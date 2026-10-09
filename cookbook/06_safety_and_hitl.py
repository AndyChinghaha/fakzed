"""Cookbook 06: control & safety — guardrails, hooks, and human-in-the-loop.

Run:  python cookbook/06_safety_and_hitl.py
"""

from _cookbook_utils import ScriptedModel

from fakzed import Agent, GuardrailError, Hooks, InputGuardrail, OutputGuardrail, tool
from fakzed.model import ModelResponse, ToolCall


# ---- 1. input guardrail: blocked before the model is called ----------------
def no_politics(data: str, context=None) -> bool:
    return "政治" not in data


@tool
def run_shell(command: str) -> str:
    """Execute a shell command. DANGEROUS."""
    return f"(simulated) ran: {command}"


# ---- 2. hooks: lifecycle callbacks -----------------------------------------
hooks = Hooks(
    on_run_start=[lambda message: print("  [hook] run started:", message[:20])],
    on_tool_call=[lambda call: print("  [hook] tool call:", call.name, call.arguments)],
    on_tool_result=[lambda call, result: print("  [hook] tool result:", result[:30])],
    on_run_end=[lambda response: print("  [hook] run ended:", response.event)],
)

model = ScriptedModel(
    responses=[
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="run_shell", arguments={"command": "rm -rf /"})],
        ),
        ModelResponse(content="命令已执行。"),
    ]
)
agent = Agent(
    name="ops-bot",
    model=model,
    instructions="你是运维助手。",
    tools=[run_shell],
    input_guardrails=[InputGuardrail(name="no_politics", check=no_politics)],
    hooks=hooks,
)

print("1) 护栏拦截测试:")
try:
    agent.run("讨论一下政治话题")
except GuardrailError as exc:
    print("   已拦截:", exc)

# ---- 3. human-in-the-loop: pause after the first tool batch ----------------
print("2) HITL 暂停测试:")
model2 = ScriptedModel(
    responses=[
        ModelResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="run_shell", arguments={"command": "rm -rf /"})],
        ),
        ModelResponse(content="好，命令已执行。"),
    ]
)
agent2 = Agent(
    name="ops-bot-2", model=model2, instructions="你是运维助手。", tools=[run_shell], hooks=hooks
)

resp = agent2.run("删除生产库", stop_after_tool_call=True)
print("   事件:", resp.event)
print(
    "   待审批工具:",
    resp.tool_call.name if resp.tool_call else None,
    resp.tool_call.arguments if resp.tool_call else "",
)

# a human reviews the tool result and approves…
approved = True
if approved:
    final = agent2.resume()
    print("   审批后继续:", final.content)


# ---- 4. output guardrail: bad output is fed back for revision ---------------
def no_secrets(data: str, context=None) -> bool:
    return "SECRET" not in data


model3 = ScriptedModel(
    responses=[
        ModelResponse(content="密码是 SECRET-123"),
        ModelResponse(content="抱歉，我不能泄露密码。"),
    ]
)
agent3 = Agent(
    name="secretary",
    model=model3,
    output_guardrails=[OutputGuardrail(name="no_secrets", check=no_secrets, retries=2)],
)
print("3) 输出护栏测试:", agent3.run("数据库密码是什么").content)
