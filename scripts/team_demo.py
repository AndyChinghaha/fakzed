"""M5 demo: a multi-expert team (researcher + analyst) coordinating itself.

Uses a scripted in-memory model so the demo runs with no network or API key.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Any

from pydantic import Field

from fakzed import Agent, Team
from fakzed.agent import TeamRoute
from fakzed.model import Message, Model, ModelResponse, Tool
from fakzed.model.base import ResponseFormat


class ScriptedModel(Model):
    """A model whose responses are scripted per scenario."""

    id: str = "scripted"
    provider: str = "fake"
    responses: list[ModelResponse] = Field(default_factory=list)

    def enqueue(self, *responses: ModelResponse) -> None:
        self.responses.extend(responses)

    def _pop(self) -> ModelResponse:
        return self.responses.pop(0) if self.responses else ModelResponse(content="")

    def response(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        return self._pop()

    def response_stream(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> Iterator[ModelResponse]:
        yield self._pop()

    async def aresponse(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        return self._pop()

    async def aresponse_stream(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        response_format: ResponseFormat | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelResponse]:
        yield self._pop()


def scenario_coordinate() -> None:
    """The leader delegates to the researcher, then the analyst, and answers."""
    researcher_model = ScriptedModel()
    researcher_model.enqueue(ModelResponse(content="Hwei 在 2024 年 T1 夺冠时的招牌英雄是阿狸"))
    analyst_model = ScriptedModel()
    analyst_model.enqueue(ModelResponse(content="该英雄出场率为 63%，被 ban 率 41%"))

    researcher = Agent(name="researcher", description="查找事实", model=researcher_model)
    analyst = Agent(name="analyst", description="分析数据", model=analyst_model)

    leader_model = ScriptedModel()
    leader_model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[
                {
                    "id": "c1",
                    "name": "transfer_to_researcher",
                    "arguments": {"task": "查 Faker 巅峰期最常用的英雄"},
                }
            ],
        )
    )
    leader_model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[
                {
                    "id": "c2",
                    "name": "transfer_to_analyst",
                    "arguments": {"task": "统计该英雄的出场与 ban 率"},
                }
            ],
        )
    )
    leader_model.enqueue(
        ModelResponse(
            content="综合结论：Faker 的阿狸既是招牌也是高价值 ban 位，双维度都验证了这一点。"
        )
    )

    team = Team(name="lol research team", model=leader_model, members=[researcher, analyst])

    response = team.run("Faker 最出名的英雄是什么？值得 ban 吗？")
    print("场景1 多专家分工（coordinate 模式）:")
    print(f"  最终回答: {response.content}")
    print("  执行历史:")
    for interaction in team.member_interactions:
        print(f"    -> {interaction.member_name}: {interaction.task}")
        print(f"       {interaction.response}")


def scenario_route() -> None:
    """The leader emits one structured route straight to the right expert."""
    analyst_model = ScriptedModel()
    analyst_model.enqueue(ModelResponse(content="按数据排序：阿狸 > 妖姬 > 沙皇"))

    researcher = Agent(name="researcher", description="查找事实", model=ScriptedModel())
    analyst = Agent(name="analyst", description="分析数据", model=analyst_model)

    leader_model = ScriptedModel()
    leader_model.enqueue(
        ModelResponse(
            content="routing",
            parsed=TeamRoute(
                member="analyst", task="把三英雄按登场率排序", reasoning="这是数据分析任务"
            ),
        )
    )

    team = Team(name="router", model=leader_model, mode="route", members=[researcher, analyst])
    response = team.run("帮我排序英雄登场率")

    print("\n场景2 结构化路由（route 模式）:")
    print(f"  路由结果: {response.content}")


def scenario_collaborate() -> None:
    """Every member works on the same task; the leader synthesizes."""
    researcher_model = ScriptedModel()
    researcher_model.enqueue(ModelResponse(content="事实：Faker 五届 S 赛冠军"))
    analyst_model = ScriptedModel()
    analyst_model.enqueue(ModelResponse(content="分析：其巅峰期横跨 2013-2024"))

    researcher = Agent(name="researcher", description="查找事实", model=researcher_model)
    analyst = Agent(name="analyst", description="分析数据", model=analyst_model)

    leader_model = ScriptedModel()
    leader_model.enqueue(
        ModelResponse(content="综合：Faker 以五冠王身份统治了超过十年的英雄联盟职业赛场。")
    )

    team = Team(
        name="panel",
        model=leader_model,
        mode="collaborate",
        members=[researcher, analyst],
    )
    response = team.run("评价 Faker 的历史地位")

    print("\n场景3 全员参与（collaborate 模式）:")
    print(f"  聚合回答: {response.content}")
    print(f"  参与成员: {[i.member_name for i in team.member_interactions]}")


if __name__ == "__main__":
    scenario_coordinate()
    scenario_route()
    scenario_collaborate()
    print("\nM5 演示完成")
