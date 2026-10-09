# Changelog

All notable changes to fakzed are documented in this file.

## [0.1.0] - 2026-10-09

First release: SDK + platform server + web console.

### SDK (`fakzed`)

- **Primitives**
  - `Agent`: tool-call loop, multi-turn sessions, streaming (`run` / `run_stream` / `arun` / `arun_stream`), Human-in-the-Loop (`stop_after_tool_call` + `resume`), structured output via `response_format`
  - `Team`: three coordination modes (coordinate / route / collaborate) with nested membership and `member_interactions` audit trail
  - `Workflow`: declarative orchestration with `Step`, `IfBlock`, `LoopBlock`, `ParallelBlock`
- **Model layer**
  - Unified `Model` interface with providers: OpenAI, DeepSeek, Anthropic, Ollama
  - Registry factory: `"deepseek:deepseek-chat"` string addressing via `create_model`
  - Streaming, tool calls, reasoning content, and structured-output parsing on every adapter
- **Capabilities**
  - `@tool` tools + built-ins (search, shell, file, http, calculator, clock) + MCP client
  - `AgenticMemory` (user memory) and Knowledge RAG (`Embedder` / `VectorDb` / `KnowledgeBase`)
  - `Skill`, `ContextProvider`, `TimeProvider`, permission callback
  - Input/output `Guardrails` and lifecycle `Hooks`
- **Operations**
  - `EventBus` / `Tracer` / `MetricsCollector` observability
  - `BackgroundRunner` and `Scheduler` runtime utilities
  - `eval_agent` evaluation harness
  - `InMemoryStorage` / `SqliteStorage` session backends

### Platform (`fakzed-server`)

- `FakzedServer`: agent registry, REST + SSE streaming API
- API-key auth per agent, admin bootstrap key, `--no-auth` mode
- Multi-tenancy with usage accounting and quota checks
- JSON-file persistence with pluggable `Storage`
- `/health` and `/metrics` monitoring endpoints
- `fakzed-server` CLI entry point
- `RemoteAgent` SDK client mirroring the local `Agent` interface

### Web console (`apps/ui`)

- Next.js 16 dashboard: agent registry, chat with SSE streaming, runs/monitoring views

### Engineering

- 238 tests, 89% coverage across both libraries
- ruff + mypy clean; CI pipeline (lint / format / types / tests)
- Docs (README, quickstart, primitives, capabilities, platform) and 8 runnable cookbook examples
- Micro-benchmarks: ~1 ms single-turn agent run (framework overhead only)
