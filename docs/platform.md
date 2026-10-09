# 平台层：fakzed-server / RemoteAgent / Web UI

SDK 与平台共享同一注册机制：本地 `Agent` 写好后，`fakzed-server` 通过注册中心把它服务化，Web 控制台和 `RemoteAgent` 客户端共享同一套 REST + SSE 接口。

```
┌─────────────┐   REST + SSE    ┌───────────────┐   HTTP     ┌──────────────┐
│  RemoteAgent │ ──────────────▶ │ fakzed-server  │ ◀───────── │  Web 控制台    │
│ （SDK 客户端） │  X-API-Key     │ FastAPI + 注册中心 │           │  Next.js UI   │
└─────────────┘                 └───────────────┘           └──────────────┘
                                      │
                                      ▼
                           SDK 能力（Storage / Runner / 观测）
```

## 1. 启动平台

```bash
# 安装
uv add fakzed-server          # workspace 内已含

# 启动
fakzed-server --host 127.0.0.1 --port 8000 \
              --db fakzed_server.json \
              --admin-key my-admin-key     # 引导管理员 key（只显示一次）
fakzed-server --no-auth                    # 内网调试可关闭认证
```

Docker 一键部署见 [根目录 docker-compose.yml](../docker-compose.yml)。

## 2. 注册 Agent

平台侧通过 `POST /api/agents` 用「模型字符串 + 指令」创建 Agent（与 SDK 的 `Agent(model="provider:model")` 同构）：

```bash
curl -X POST http://127.0.0.1:8000/api/agents \
  -H "X-API-Key: my-admin-key" -H "Content-Type: application/json" \
  -d '{"name":"hello","model":"deepseek:deepseek-chat",
       "instructions":"你是简洁的中文助手","api_key":"sk-..."}'
```

代码内嵌（复用同一个注册中心对象）：

```python
from fakzed import Agent
from fakzed_server.app import FakzedServer
from fakzed_server.registry import AgentRegistry

registry = AgentRegistry()
registry.register(Agent(name="hello", model="deepseek:deepseek-chat"))

server = FakzedServer(admin_api_key="my-admin-key", storage=...)  # registry 可注入
```

## 3. 对话 API

| 端点 | 说明 |
|------|------|
| `POST /api/agents/{name}/chat` | 同步对话，返回 `RunResponse` 全字段 JSON（含 `session_id`） |
| `POST /api/agents/{name}/chat/stream` | SSE 流式（`data: {type: "content"|"tool_call"|"tool_call_completed"|"done", ...}`） |
| `POST /api/agents/{name}/resume` | HITL 恢复（`stop_after_tool_call` 暂停后） |
| `GET /api/sessions/{session_id}` | 会话消息历史 |
| `GET /api/agents` / `PATCH` / `DELETE` | 管理（启停/删除，admin） |

认证：`X-API-Key` 请求头。key 服务端只存 SHA-256 哈希，签发时一次性返回原文；`user` / `admin` 两级角色，管理端点仅 admin。

## 4. RemoteAgent：SDK 远程调用

与本地 `Agent` 完全同构的接口，urllib 实现、零新依赖：

```python
from fakzed import RemoteAgent

server = RemoteAgent(
    name="hello",
    base_url="http://127.0.0.1:8000",
    api_key="my-admin-key",
)

resp = server.run("你好")  # RunResponse
for chunk in server.run_stream("你好"):
    ...  # SSE 流式
resp = await server.arun("你好")  # 异步
await server.aresume()  # HITL

# 会话恢复：RemoteAgent 自动捕获 session_id 回放
server2 = RemoteAgent(name="hello", base_url=..., api_key=..., session_id=resp.session_id)
server2.run("继续")
```

## 5. 运行管理与监控

| 端点 | 说明 |
|------|------|
| `POST /api/runs` + `GET /api/runs` + `GET /api/runs/{id}` + `POST .../cancel` | 后台执行（复用 SDK `BackgroundRunner`），运行记录 JsonStore 原子写落盘、跨进程恢复 |
| `GET /api/events` | 事件流（复用 SDK `EventBus`） |
| `GET /api/traces` | 运行追踪（复用 SDK `Tracer`） |
| `GET /api/metrics/summary` | 成本/延迟聚合（复用 SDK `MetricsCollector`） |

## 6. 多租户

`User` → `Organization` → `Project` 三级 + `Membership`：

- Agent 按 `project_id` 作用域隔离
- API key 绑定 user，签发/吊销：`POST /api/keys` / `DELETE /api/keys/{key_id}`
- 租户管理端点：`POST /api/tenants/users|orgs|projects`

## 7. Web 控制台（apps/ui）

Next.js 16 控制台，浏览器完成「创建 Agent → 对话调试 → 查看追踪与成本」全流程：

- **对话页**：流式 Markdown、工具调用折叠、HITL 审批按钮、`?session=` 续传
- **Agent 页**：列表/创建/启停/删除
- **会话页**：历史会话与消息详情
- **监控页**：运行列表、事件/追踪、成本延迟
- **设置页**：API key 签发/吊销（原文只展示一次）、平台地址（localStorage 持久化）

```bash
cd apps/ui
npm install
npm run dev      # http://localhost:3000，平台地址在设置页配置
```

前端 SDK（`apps/ui/src/lib/api.ts`）即 REST + SSE 客户端，可参考实现任何语言的 `RemoteAgent`。
