# fakzed

A lightweight Python framework for building agent platforms.

- **Three primitives**: `Agent` (tool loop + multi-turn), `Team` (coordinate /
  route / collaborate), `Workflow` (sequential / conditional / loop / parallel)
- **Own model layer**: OpenAI / DeepSeek / Anthropic / Ollama adapters with a
  registry factory (`"deepseek:deepseek-chat"`), streaming, tool calls,
  reasoning content, structured output
- **Pluggable capabilities**: `@tool` + built-ins + MCP client, AgenticMemory,
  Knowledge RAG, Skills, ContextProvider, Guardrails, Hooks, observability
- **Runtime**: BackgroundRunner, Scheduler, Evals

```bash
uv add fakzed            # or: pip install fakzed
uv add fakzed[deepseek]  # provider extras: openai / anthropic / ollama / deepseek / sqlite

# China users: add a mirror if direct PyPI access stalls (copy-paste ready)
uv add fakzed --index-url https://mirrors.cloud.tencent.com/pypi/simple
pip install fakzed -i https://mirrors.cloud.tencent.com/pypi/simple
```

```python
from fakzed import Agent, tool


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


agent = Agent(name="calc", model="deepseek:deepseek-chat", tools=[add])
resp = agent.run("1 + 1 = ?")
print(resp.content)
```

See the monorepo [README](../../README.md), [docs](../../docs/quickstart.md)
and [cookbook](../../cookbook/README.md) for the full guide.
