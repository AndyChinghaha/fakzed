"""Cookbook 05: Workflow — declarative orchestration with control flow.

Run:  python cookbook/05_workflow.py
"""

from _cookbook_utils import scripted

from fakzed import Agent, IfBlock, LoopBlock, ParallelBlock, Step, Workflow

# Steps can run agents or plain functions; here we use scripted agents and
# functions so the example needs no API key.

planner = Agent(name="planner", model=scripted("计划：先调研，再成文，最后校对。"))
writer = Agent(name="writer", model=scripted("正文：fakzed 是一个轻量级 Agent 框架。"))


def upper(text: str, ctx) -> str:
    """Plain-function step: receives (text, context)."""
    ctx.session_data["touched"] = True
    return text.upper()


def pick_longer(outputs: list[str], ctx) -> str:
    """ParallelBlock join: fan-in two outputs into one."""
    return max(outputs, key=len)


workflow = Workflow(
    name="doc-pipeline",
    items=[
        Step(id="plan", agent=planner),
        Step(id="write", agent=writer, input_from="plan"),  # data flow
        Step(id="shout", function=upper, input_from="write"),  # function step
        IfBlock(  # conditional
            condition=lambda ctx: "FAKZED" in ctx.step_outputs.get("shout", ""),
            then=[Step(id="yes", function=lambda t, c: "条件命中 ✓")],
            otherwise=[Step(id="no", function=lambda t, c: "未命中")],
        ),
        LoopBlock(  # loop
            steps=[
                Step(
                    id="tick",
                    function=lambda t, c: (
                        c.session_data.update(count=c.session_data.get("count", 0) + 1) or "tick"
                    ),
                )
            ],
            until=lambda ctx: ctx.session_data.get("count", 0) >= 3,
            max_iterations=5,
        ),
        ParallelBlock(  # parallel fan-out
            steps=[
                Step(id="p1", function=lambda t, c: "first " + t),
                Step(id="p2", function=lambda t, c: "second " + t),
            ],
            join=pick_longer,
        ),
    ],
)

result = workflow.run("写一篇关于 fakzed 的文章")
print("最终输出:", result.content)
print("步骤输出:", {k: v[:30] for k, v in result.outputs.items()})
print("错误:", result.errors or "无")
