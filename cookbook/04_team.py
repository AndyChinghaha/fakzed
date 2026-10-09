"""Cookbook 04: Team — three coordination modes.

Run:  python cookbook/04_team.py
"""

from _cookbook_utils import ScriptedModel

from fakzed import Agent, Team
from fakzed.agent import TeamRoute
from fakzed.model import ModelResponse, ToolCall


def member(name: str, answer: str, description: str) -> tuple[Agent, ScriptedModel]:
    model = ScriptedModel(responses=[ModelResponse(content=answer)])
    return Agent(name=name, description=description, model=model), model


# ---- mode 1: coordinate — leader delegates via transfer_to_* tools ----------
researcher, _ = member("researcher", "调研结论：fakzed 的原语设计简洁。", "does research")
writer, _ = member("writer", "文案：fakzed，一个值得一试的 Agent 框架。", "writes copy")

leader = ScriptedModel(
    responses=[
        ModelResponse(
            content="",
            tool_calls=[
                ToolCall(id="c1", name="transfer_to_researcher", arguments={"task": "调研 fakzed"}),
                ToolCall(id="c2", name="transfer_to_writer", arguments={"task": "写一句话文案"}),
            ],
        ),
        ModelResponse(content="调研和文案都完成了。"),
    ]
)
team = Team(name="content-team", model=leader, members=[researcher, writer], mode="coordinate")
print("coordinate:", team.run("做个产品宣传").content)
print("  委派记录:", [(i.member_name, i.task) for i in team.member_interactions])

# ---- mode 2: route — leader picks exactly one member -------------------------
r2, _ = member("researcher", "调研结论：fakzed 的原语设计简洁。", "does research")
w2, _ = member("writer", "文案：fakzed，一个值得一试的 Agent 框架。", "writes copy")
router = ScriptedModel(
    responses=[
        ModelResponse(parsed=TeamRoute(member="writer", task="写一段话", reasoning="写作任务"))
    ]
)
route_team = Team(name="routing", model=router, members=[r2, w2], mode="route")
print("route     :", route_team.run("写一段话").content)

# ---- mode 3: collaborate — all members run, leader synthesizes --------------
r3, _ = member("researcher", "调研结论：fakzed 的原语设计简洁。", "does research")
w3, _ = member("writer", "文案：fakzed，一个值得一试的 Agent 框架。", "writes copy")
synth = ScriptedModel(responses=[ModelResponse(content="综合：设计简洁 + 文案出色。")])
collab = Team(name="review", model=synth, members=[r3, w3], mode="collaborate")
print("collaborate:", collab.run("评估 fakzed").content)
print("  全员产出:", [i.response for i in collab.member_interactions])
