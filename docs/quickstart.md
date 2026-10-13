# Quickstart：5 分钟跑通第一个 Agent

## 1. 安装

SDK 包名是 `fakzed`。推荐用 uv（并行下载，实测比 pip 快约 5 倍）：

```bash
uv add fakzed            # uv 用户
pip install fakzed       # pip 用户
```

**国内网络直连 PyPI 会卡住**，安装时请加镜像源（复制即用，实测冷启动约 10 秒）：

```bash
uv add fakzed --index-url https://mirrors.cloud.tencent.com/pypi/simple
pip install fakzed -i https://mirrors.cloud.tencent.com/pypi/simple
```

模型适配器按需安装，均为可选依赖（同样支持 `--index-url` 镜像参数）：

```bash
uv add "fakzed[deepseek]"    # DeepSeek（一等支持）
uv add "fakzed[openai]"      # OpenAI / 兼容端点
uv add "fakzed[anthropic]"   # Anthropic Claude
uv add "fakzed[ollama]"      # 本地 Ollama
uv add "fakzed[sqlite]"      # SQLite 会话持久化
```

## 2. 配置模型

四种用法，从简到繁：

```python
from fakzed import Agent, create_model

# ① 字符串寻址："provider:model-name"
agent = Agent(model="deepseek:deepseek-chat")

# ② 工厂函数 + 自定义参数
model = create_model(
    "deepseek:deepseek-chat",
    base_url="https://api.deepseek.com/v1",  # 默认已内置，可覆盖
    api_key="sk-...",  # 不传则读环境变量 DEEPSEEK_API_KEY
)
agent = Agent(model=model)

# ③ 直接实例化适配器
from fakzed.model.provider import DeepSeekChat

agent = Agent(model=DeepSeekChat(id="deepseek-chat"))

# ④ 环境变量自动回退
#    DeepSeek → DEEPSEEK_API_KEY；OpenAI → OPENAI_API_KEY
#    Anthropic → ANTHROPIC_API_KEY；Ollama → 本地 11434 端口
```

> **没有 API Key 也能跑**：Cookbook 示例使用 `ScriptedModel`（脚本式假模型，
> 见 `cookbook/_cookbook_utils.py`），答案预设、零网络请求，所有示例开箱即跑；
> 换成 `model = "deepseek:deepseek-chat"` 即接真实模型（读 DEEPSEEK_API_KEY）。

## 3. 第一个 Agent

```python
from fakzed import Agent

agent = Agent(
    name="hello-bot",
    model="deepseek:deepseek-chat",
    instructions="你是一个简洁的中文助手，回答不超过三句话。",
)

response = agent.run("用一句话介绍你自己")
print(response.content)
```

`run()` 返回 `RunResponse`，核心字段：

| 字段 | 含义 |
|------|------|
| `content` | 最终文本答案 |
| `reasoning_content` | 推理模型的思维链（DeepSeek-R1 等） |
| `messages` | 本轮全部消息（含工具消息） |
| `usage` | token 用量（prompt/completion） |
| `tool_call` / `tool_call_result` | 最后一轮工具调用（HITL 暂停时） |
| `event` | `complete` / `paused` 等运行事件 |
| `agent.session_id` | 会话 ID（自动创建，可持久化恢复） |

## 4. 流式输出与打印

```python
# 富文本打印（rich）
agent.print_response("介绍一下你自己", stream=True)

# 流式迭代
for chunk in agent.run_stream("写一首四行诗"):
    print(chunk.content, end="")

# 异步
response = await agent.arun("你好")
async for chunk in agent.arun_stream("你好"):
    ...
```

## 5. 给 Agent 一个工具

```python
from fakzed import Agent, tool


@tool
def calculator(expression: str) -> str:
    """计算数学表达式，支持 + - * / 与括号。"""
    ...


agent = Agent(
    model="deepseek:deepseek-chat",
    tools=[calculator],
)
agent.print_response("帮我算一下 (12 + 30) * 2 等于多少", stream=True)
```

模型会自动发起工具调用，`run` 循环执行并把结果回传给模型，直到得到最终答案。

## 6. 下一步

| 想做什么 | 去哪里 |
|----------|--------|
| 深入了解三个原语 | [primitives.md](primitives.md) |
| 记忆 / 知识 / 护栏 / 运维 | [capabilities.md](capabilities.md) |
| 把 Agent 部署成平台 + Web UI | [platform.md](platform.md) |
| 直接抄代码 | [cookbook/](../cookbook/) |
