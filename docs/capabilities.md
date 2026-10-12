# 能力专题：工具 / 记忆 / 知识 / 控制 / 运维

fakzed 的核心保持精简，其余能力全部插件化挂载到 `Agent` 上。

## 1. 工具（Tools）

### 定义工具

```python
from fakzed import tool


@tool
def calculator(expression: str) -> str:
    """计算数学表达式，支持 + - * / 与括号。"""
    return str(eval_whitelist(expression))


@tool(name="query_db", description="查询用户数据库", dangerous=False)
async def query_db(sql: str) -> str: ...  # async 工具同样支持，自动桥接同步 call 与异步 acall
```

- 函数签名自动生成参数 schema（pydantic 校验，非法参数直接报错不执行）
- `@tool` 支持 `name` / `description` / `dangerous` 覆写
- 挂载：`Agent(tools=[...])`，模型通过 function-calling 自动调用

### 工具包（ToolKit）

```python
from fakzed.tools import ToolKit

class MyToolKit(ToolKit):
    # 定义 name + tools 后，Agent(toolkits=[...]) 自动挂载并注入 instructions
```

### 内置工具集

`fakzed.tools.builtin`：`calculator`（AST 白名单安全计算）、`read_file`、`write_file`、`run_shell`、`url_read`、`web_search`（DDG HTML 端点，无需 key）。

### MCP 客户端

```python
from fakzed.tools.mcp import MCPServer

mcp = MCPServer(command="python", args=["echo_server.py"])
agent = Agent(model=..., tools=[mcp.as_tools()])
```

MCP 2.x SDK 懒加载，stdio 传输；工具调用经 `arun` 绑定到运行中的事件循环。

### 权限系统

```python
agent = Agent(
    tools=[dangerous_tool],
    tool_permission_handler=lambda tool, args: input(f"允许 {tool.name}? (y/n)") == "y",
    # 或任何策略函数；抛异常/返回 False 默认拒绝，拒绝消息回馈模型
)
```

## 2. 记忆（AgenticMemory）

用户级长期记忆，跨会话保留，随系统提示词注入。

```python
from fakzed import Agent, AgenticMemory
from fakzed.storage import SqliteStorage

storage = SqliteStorage(path="memory.db")
memory = AgenticMemory(storage=storage, user_id="alice")

agent = Agent(
    model=...,
    memory=memory,  # 自动注入 add_to_memory / search_memory 工具
    storage=storage,
    user_id="alice",
)
```

模型可自主调用 `add_to_memory` 记录用户偏好，`search_memory` 检索；也可代码直调：

```python
memory.add_memory("用户偏好：回答用中文，风格简洁")
memory.search_memories("偏好")
```

### 会话摘要压缩

长对话自动压缩（配合 SQLite 自动迁移 summary 列）：

```python
Agent(summarize=True, summarize_threshold=20, summarize_keep=6)
# 历史超过 20 条时把旧消息压缩成摘要，保留最近 6 条，摘要作为 system 前缀注入
```

## 3. 知识（Knowledge RAG）

```python
from fakzed import Agent, HashEmbedder, InMemoryVectorDb, KnowledgeBase

kb = KnowledgeBase(
    embedder=HashEmbedder(),  # 本地哈希嵌入，零依赖零 key（生产换 OpenAIEmbedder）
    vector_db=InMemoryVectorDb(),
)
kb.add_text("产品手册：fakzed 是一款……", metadata={"source": "manual"})
kb.add_file("docs/readme.txt")  # 按段落分块

agent = Agent(model=..., knowledge=kb)  # 相关片段自动注入 system 提示词
agent.run("fakzed 是什么？")
```

管道：分块 → 嵌入 → 向量索引 → 相似检索 Top-K → 注入提示词。`Embedder` / `VectorDb` 均为接口，可替换为生产实现。

## 4. 动态上下文（ContextProvider）

```python
from fakzed import Agent, ContextProvider, TimeProvider

agent = Agent(
    model=...,
    context_providers=[
        TimeProvider(),  # 注入当前时间
        ContextProvider("project", getter=lambda: {"name": "fakzed"}),
    ],
)
```

`instructions` 支持 `{{变量}}` 模板，运行时 `run(..., context={...})` 渲染。

## 5. 控制与安全

### Guardrails（护栏）

```python
from fakzed import Guardrails, InputGuardrail, OutputGuardrail


def no_politics(text: str):
    return False if "政治" in text else True  # 返回 bool/str/GuardrailResult 均可


agent = Agent(
    model=...,
    input_guardrails=[
        InputGuardrail("no_politics", no_politics)
    ],  # 失败抛 GuardrailError，模型不被调用
    output_guardrails=[OutputGuardrail("no_leak", no_secrets, retries=2)],  # 失败把原因回传模型修订
)
```

### Hooks（生命周期回调）

```python
from fakzed import Hooks

hooks = Hooks(
    on_run_start=lambda agent, msg: print("run start"),
    on_run_end=lambda agent, resp: print("run end"),
    on_tool_call=lambda agent, name, args: print(f"tool {name}"),
    on_tool_result=lambda agent, name, result: print("tool done"),
)
agent = Agent(model=..., hooks=hooks)
# Workflow 另有 on_step_complete 步骤级回调；hook 异常被吞不影响主流程
```

### Human-in-the-Loop

```python
resp = agent.run("帮我删掉生产库的 user 表", stop_after_tool_call=True)
print(resp.event)  # "paused"
print(resp.tool_call)  # {"name": "run_shell", "arguments": {...}}

if approve:
    final = agent.resume()  # 从暂停点继续循环（异步用 aresume）
```

## 6. 可观测性与运维

### RunObserver 一站式埋点

```python
from fakzed import EventBus, MetricsCollector, RunObserver

observer = RunObserver(event_bus=EventBus(), metrics=MetricsCollector())
agent = Agent(model=..., observer=observer)
```

- **事件**：`RunEvent`（run_id/agent_id/时间戳），发布订阅 + 有界 history + drain 回收
- **追踪**：`Tracer` 收集完整 `TraceSpan` 树；默认 NOOP 零开销
- **指标**：`RunMetrics`（token/延迟/工具调用次数/迭代数），`MetricsCollector.summary()` 聚合总量与均值

### Evals 评估

```python
from fakzed import EvalCase, eval_agent

cases = [
    EvalCase(name="greet", input="你好", expected="好"),
    EvalCase(name="math", input="1+1", expected="2"),
]
report = eval_agent(agent, cases)  # 默认 contains_judge 子串判定，可自定义 judge
print(report.accuracy)  # passed / total
```

### 后台执行与调度

```python
from fakzed import BackgroundRunner, Scheduler

runner = BackgroundRunner()
run_id = runner.submit(agent.run, "长任务")
run = runner.wait(run_id)  # 轮询，RunStatus: completed/failed/cancelled
runner.cancel(run_id)

scheduler = Scheduler()
scheduler.add_job(fn, interval_seconds=60)  # 守护线程 tick 执行
scheduler.remove_job(job_id)
```

## 7. Skills

```python
from fakzed import Skill

@tool
def search_case_law(keyword: str) -> str:
    """在判例库中搜索关键词。"""
    ...

skill = Skill(
    name="legal-review",
    description="审查合同时启用",
    instructions="你是资深合同评审员……",
    tools=[search_case_law],  # 技能自带工具，挂载后自动生效
)
agent = Agent(model=..., skills=[skill])  # 指令 + 工具一并注入
```
