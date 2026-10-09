"""M6 demo: the deterministic "collect -> analyze -> report" pipeline.

Uses scripted agents/functions so the demo runs with no network or API key.
"""

from team_demo import ScriptedModel

from fakzed import Agent, Workflow, WorkflowContext
from fakzed.model import ModelResponse
from fakzed.workflow import IfBlock, LoopBlock, ParallelBlock, Step


def scenario_pipeline() -> None:
    def collect(input: str, ctx: WorkflowContext) -> str:
        ctx.session_data["source"] = "电竞数据 API"
        return f"原始数据：{input} 相关战绩 100 条"

    analyst_model = ScriptedModel()
    analyst_model.enqueue(
        ModelResponse(content="分析结论：Faker 阿狸胜率 71%，是当前版本 T1 级中单")
    )
    analyst = Agent(name="analyst", model=analyst_model)

    def report(input: str, ctx: WorkflowContext) -> str:
        return f"【报告】{input}（数据来源：{ctx.session_data['source']}）"

    workflow = Workflow(
        name="collect-analyze-report",
        items=[
            Step(id="collect", function=collect),
            Step(id="analyze", agent=analyst, input_from="collect"),
            Step(id="report", function=report, input_from="analyze"),
        ],
    )

    result = workflow.run("Faker 近期比赛")
    print("场景1 采集 -> 分析 -> 报告 流水线:")
    print(f"  最终输出: {result.content}")
    print(f"  各步骤输出: {result.outputs}")


def scenario_control_flow() -> None:
    def count(input: str, ctx: WorkflowContext) -> str:
        ctx.session_data["total"] = ctx.session_data.get("total", 0) + int(input)
        return str(ctx.session_data["total"])

    def summarize(input: str, ctx: WorkflowContext) -> str:
        return f"汇总完成：总积分 {ctx.session_data['total']}"

    workflow = Workflow(
        name="score-loop",
        items=[
            LoopBlock(
                steps=[Step(id="add", function=count)],
                until=lambda ctx: ctx.session_data["total"] >= 10,
                max_iterations=10,
            ),
            IfBlock(
                condition=lambda ctx: ctx.session_data["total"] >= 10,
                then=[Step(id="pass", function=summarize)],
            ),
        ],
    )

    result = workflow.run("3")
    print("\n场景2 循环累加 + 条件分支:")
    print(f"  输出: {result.content}")


def scenario_parallel() -> None:
    import time

    def slow_label(input: str, ctx: WorkflowContext) -> str:
        time.sleep(0.3)
        return "数据维1：英雄胜率"

    def slow_other(input: str, ctx: WorkflowContext) -> str:
        time.sleep(0.3)
        return "数据维2：经济曲线"

    def join(outputs: list[str], ctx: WorkflowContext) -> str:
        return "双通道汇总 -> " + " + ".join(outputs)

    workflow = Workflow(
        name="parallel-fetch",
        items=[
            ParallelBlock(
                steps=[
                    Step(id="stats", function=slow_label),
                    Step(id="economy", function=slow_other),
                ],
                join=join,
            ),
        ],
    )

    result = workflow.run("x")
    print("\n场景3 并行 fan-out/fan-in:")
    print(f"  输出: {result.content}")


if __name__ == "__main__":
    scenario_pipeline()
    scenario_control_flow()
    scenario_parallel()
    print("\nM6 演示完成")
