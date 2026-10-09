# 三原语指南：Agent / Team / Workflow

fakzed 的核心只有三个原语，覆盖单智能体、多智能体协作、确定性编排三类场景。

## 1. Agent：工具循环单智能体

### 基础构造

```python
from fakzed import Agent

agent = Agent(
    name="researcher",
    description="网络调研专家",
    model="deepseek:deepseek-chat",
    instructions="调研要引用来源，结论要分点列出。",
    tools=[...],
    max_iterations=5,  # 工具循环上限，防死循环
)
```

关键字段（全部可选）：

| 字段 | 说明 |
|------|------|
| `model` | `Model` 实例或 `"provider:model"` 字符串 |
| `instructions` | 系统指令，字符串或列表（列表拼接） |
| `tools` / `toolkits` | 工具列表 / 工具包（instructions 自动注入） |
| `markdown` | 强制 Markdown 输出 |
| `max_iterations` | 单轮工具循环最大迭代次数 |

### 四种运行路径

```python
resp = agent.run("调研一下核聚变进展")  # 同步
resp = await agent.arun("...")  # 异步
for chunk in agent.run_stream("..."):
    pass  # 同步流式
async for chunk in agent.arun_stream("..."):
    pass  # 异步流式
```

`{{变量}}` 模板渲染 + 运行期上下文：

```python
agent = Agent(instructions="你是{{role}}。")
agent.run("你好", context={"role": "财务分析师"})
```

### 会话与恢复

```python
resp = agent.run("我叫小明")  # 自动创建 session，返回 session_id
resp2 = agent.run("我叫什么？")  # 同实例自动带上历史

# 跨实例/跨进程恢复
restored = Agent(model=..., session_id=resp.session_id, storage=SqliteStorage(path="agent.db"))
restored.run("继续上一个话题")
```

`storage` 支持 `InMemoryStorage`（默认）与 `SqliteStorage`（WAL 模式，`.db` 文件持久化）。

## 2. Team：多智能体协作

`Team` 继承 `Agent`——团队本身就是 leader，天然支持嵌套（团队作为另一个团队的成员）。

```python
from fakzed import Agent, Team

researcher = Agent(name="researcher", model=..., instructions="做调研")
writer = Agent(name="writer", model=..., instructions="写文案")

team = Team(
    name="content-team",
    model=...,
    members=[researcher, writer],
    mode="coordinate",
)
```

### 三种协作模式

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `coordinate` | leader 自行回答，通过 `transfer_to_*` 工具把任务委派给成员，汇总结果 | 有主见的总管模式 |
| `route` | leader 产出结构化 `TeamRoute`（成员/任务/理由），只派给最合适的一个成员 | 明确分工的调度模式 |
| `collaborate` | 全员并行执行同一任务，leader 汇总综合出最终答案 | 多视角审议模式 |

### 共享与隔离

```python
team = Team(
    members=[researcher, writer],
    share_model=True,  # 成员继承 team 的 model（默认 True）
    share_context=True,  # 成员继承 storage/user_id（默认 True）
)
```

成员会话按 `{team_session}:{member_slug}` 独立持久化；每次委派记录 `MemberInteraction`（task → member → answer）。

## 3. Workflow：声明式编排

把 Agent 当步骤，用控制流拼接成确定性流程。

```python
from fakzed import Agent, Step, Workflow

planner = Agent(name="planner", model=...)
writer = Agent(name="writer", model=...)


def summarize(text: str, ctx) -> str:
    return f"摘要：{text[:100]}"


workflow = Workflow(
    name="pipeline",
    items=[
        Step(id="plan", agent=planner),
        Step(id="write", agent=writer, input_from="plan"),  # 用 plan 的输出当输入
        Step(id="digest", function=summarize, input_from="write"),
    ],
)

result = workflow.run("写一篇关于猫的短文")
print(result.content)  # 最终输出
print(result.outputs)  # {"plan": ..., "write": ..., "digest": ...}
```

### 执行体与数据传递

`Step` 支持四种执行体：`agent`（Agent.run）、`function`（普通函数/协程）、`workflow`（嵌套 Workflow）、Team（Agent 子类，直接放 `agent=`）。

- 默认输入 = 流程初始输入；`input_from="step_id"` 绑定上游步骤输出
- `WorkflowContext.session_data` 跨步骤共享可变状态
- 函数签名：`fn(text: str, ctx: WorkflowContext) -> str`

### 控制流

```python
from fakzed import IfBlock, LoopBlock, ParallelBlock, Step

steps = [
    Step(id="think", agent=planner),
    IfBlock(                       # 条件分支
        condition=lambda text, ctx: "需要" in text,
        then=[Step(id="a", ...)],
        otherwise=[Step(id="b", ...)],
    ),
    LoopBlock(                     # 循环（带保护上限）
        steps=[Step(id="iter", ...)],
        until=lambda text, ctx: ctx.session_data.get("done", False),
        max_iterations=3,
    ),
    ParallelBlock(                 # 并行 fan-out（线程池），join 回调 fan-in 聚合
        steps=[Step(id="p1", ...), Step(id="p2", ...)],
        join=lambda outputs: "；".join(outputs),
    ),
]

workflow = Workflow(items=steps)
```

### 失败处理与异步

```python
Step(id="flaky", agent=..., retries=2, timeout=10.0)  # 重试 + 超时
# 错误默认记录在 outputs 中继续；fail_fast=True 时抛 WorkflowError

await workflow.arun("...")  # asyncio.gather 并行分支的异步路径
```
