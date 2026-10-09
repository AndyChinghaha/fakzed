# fakzed

[![PyPI version](https://img.shields.io/pypi/v/fakzed)](https://pypi.org/project/fakzed/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> A lightweight Python framework for building agent platforms.
> Named after Faker's legendary Zed outplay.

**fakzed** 是一个轻量级 Agent 开发框架：核心精简，能力插件化，SDK 与平台共享同一套注册机制。三个原语（`Agent` / `Team` / `Workflow`）加一套可插拔能力（模型、工具、记忆、知识、护栏、Hooks、可观测性），十分钟内跑通第一个 Agent，一天内部署成平台。

## 特性

- **三个原语**：`Agent`（工具循环 + 多轮对话）、`Team`（coordinate / route / collaborate 三种协作模式，可无限嵌套）、`Workflow`（声明式编排：顺序 / 条件 / 循环 / 并行）
- **自研 Model 抽象层**：OpenAI / DeepSeek / Anthropic / Ollama 四家适配 + 注册工厂（`"deepseek:deepseek-chat"` 字符串寻址），流式、工具调用、推理内容、结构化输出全链路
- **可插拔能力**：`@tool` 工具（含内置 6 件套 + MCP 客户端）、AgenticMemory 用户记忆、Knowledge RAG（Embedder + VectorDb + KnowledgeBase）、Skills、ContextProvider、权限回调
- **控制与安全**：输入/输出 Guardrails、生命周期 Hooks、Human-in-the-Loop（`stop_after_tool_call` + `resume`）
- **运维能力**：事件总线、Trace 追踪、RunMetrics 指标、Token 用量统计与成本追踪（`total_usage` / `total_cost`）、Evals 评估框架、BackgroundRunner 后台执行、Scheduler 调度器
- **平台层**：`fakzed-server`（FastAPI：注册中心 / REST + SSE / API Key 认证 / 多租户 / 持久化 / 监控 API）+ `RemoteAgent`（SDK 远程调用同构接口）+ Next.js Web 控制台

## 仓库结构

```
libs/
  fakzed/          # SDK：三个原语 + 能力层（pip install fakzed）
  fakzed-server/   # 平台层：FastAPI 服务（fakzed-server CLI）
apps/ui/           # Web 控制台（Next.js 16）
cookbook/          # 示例集：从第一个 Agent 到平台部署
docs/              # 文档：Quickstart / 原语指南 / 能力专题 / 平台
scripts/           # 演示与冒烟脚本（team_demo / workflow_demo / server_demo）
```

## 快速开始

```bash
# 1. 安装
uv add fakzed            # 或 pip install fakzed
uv add fakzed[deepseek]  # 需要 DeepSeek 时

# 2. 设置 API Key（以 DeepSeek 为例，也支持 OPENAI_API_KEY 等）
$env:DEEPSEEK_API_KEY = "sk-..."

# 3. 跑通第一个 Agent
python cookbook/01_hello_agent.py
```

```python
from fakzed import Agent

agent = Agent(
    model="deepseek:deepseek-chat",
    instructions="你是简洁的中文助手。",
)
agent.print_response("用一句话介绍你自己")
```

## 平台部署

```bash
# 启动平台（SDK 注册机制与平台共享）
fakzed-server --admin-key my-admin-key          # http://127.0.0.1:8000

# SDK 侧像调用本地 Agent 一样调用远端 Agent
from fakzed import RemoteAgent

server = RemoteAgent(name="hello", base_url="http://127.0.0.1:8000", api_key="my-admin-key")
server.run("你好")
```

Web 控制台：`docker compose up -d` 一键启动平台 + UI（见 [Docker](#docker)），或本地 `npm run dev`（apps/ui）。

## 文档

| 文档 | 内容 |
|------|------|
| [docs/quickstart.md](docs/quickstart.md) | 5 分钟上手：安装、模型、第一个 Agent |
| [docs/primitives.md](docs/primitives.md) | 三原语指南：Agent / Team / Workflow |
| [docs/capabilities.md](docs/capabilities.md) | 能力专题：工具 / 记忆 / 知识 / 护栏 / Hooks / HITL / 运维 |
| [docs/platform.md](docs/platform.md) | 平台层：fakzed-server、RemoteAgent、Web UI、多租户 |
| [cookbook/](cookbook/) | 可运行示例集（无 API Key 也可跑通） |

## 开发

```bash
uv sync --all-packages      # 安装 workspace + dev 依赖
uv run pytest               # 302 测试
uv run ruff check libs      # lint
uv run mypy libs/fakzed/src libs/fakzed-server/src   # 类型检查
```

## Docker

```bash
docker compose up -d        # fakzed-server（:8000）+ Web UI（:3000）
```

## License

MIT
