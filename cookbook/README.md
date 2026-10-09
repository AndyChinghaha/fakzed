# Cookbook：从第一个 Agent 到平台部署

全部示例**开箱即跑**（无需 API Key、无需网络）——每个示例使用 `_cookbook_utils.ScriptedModel` 脚本化模型。想换真实模型时，把 `scripted(...)` / `ScriptedModel(...)` 替换为模型字符串即可：

```python
model = "deepseek:deepseek-chat"  # 自动读取 DEEPSEEK_API_KEY
```

运行方式（在仓库根目录）：

```bash
uv run python cookbook/01_hello_agent.py
```

| 示例 | 内容 | 涉及能力 |
|------|------|----------|
| [01_hello_agent.py](01_hello_agent.py) | 第一个 Agent：四种运行路径（run/arun/run_stream/arun_stream） | Agent 基础 |
| [02_tools_and_streaming.py](02_tools_and_streaming.py) | 工具循环：模型发起工具调用 → 循环执行 → 继续回答 | @tool |
| [03_memory_and_knowledge.py](03_memory_and_knowledge.py) | 用户记忆 + RAG 知识库注入 | AgenticMemory、KnowledgeBase |
| [04_team.py](04_team.py) | 团队三种协作模式：coordinate / route / collaborate | Team、委派、路由、聚合 |
| [05_workflow.py](05_workflow.py) | 声明式编排：数据传递、条件、循环、并行 | Workflow、IfBlock、LoopBlock、ParallelBlock |
| [06_safety_and_hitl.py](06_safety_and_hitl.py) | 输入/输出护栏、生命周期 Hooks、人工审批暂停恢复 | Guardrails、Hooks、HITL |
| [07_observability.py](07_observability.py) | 事件、指标、Evals、后台执行、调度器 | RunObserver、eval_agent、BackgroundRunner、Scheduler |
| [08_platform.py](08_platform.py) | 平台部署：真实 fakzed-server + SDK RemoteAgent 端到端 | fakzed-server、RemoteAgent |

## 从 0 到平台的路

1. **01-02**：本地 Agent + 工具，理解 run 循环
2. **03**：加上记忆与知识，Agent 有长期上下文
3. **04-05**：需要协作/确定性流程时引入 Team 与 Workflow
4. **06-07**：上线前的护栏、人工审批、可观测性
5. **08**：部署为平台，SDK 远程调用 + Web 控制台
