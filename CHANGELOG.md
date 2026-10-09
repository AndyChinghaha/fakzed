# Changelog

All notable changes to fakzed are documented in this file.

## [Unreleased]

### SDK (`fakzed`)

- **Token usage tracking**: cumulative `Agent.total_usage` / `Agent.total_cost` across runs, `reset_usage()`; per-run usage now sums every model call (multi-iteration tool loops included), not just the first
- **Cost estimation**: `fakzed.model.pricing` with a reference `MODEL_PRICING` table (DeepSeek / OpenAI / Anthropic / local), `estimate_cost`, `find_price` (family-prefix matching), and `merge_usage`; `RunMetrics.cost_usd` is populated automatically
- **Performance**: state tools are built once and cached (lazy `get_state_tools`), ~23x faster single-turn `agent.run`
- **Robustness**: fixed a crash in the Ollama adapter's JSON fallback for malformed tool-call arguments

### Platform (`fakzed-server`)

- **Rate limiting**: sliding-window limiter (default 300 req/min per API key or client IP, configurable via `rate_limit_per_minute` / `--rate-limit`), 429 with `Retry-After`; `/healthz` exempt
- **CORS control**: `cors_origins` option / `--cors-origins` CLI flag to restrict allowed origins (still `*` by default for dev)
- **Key hardening**: `/api/keys` rejects unknown roles; the bootstrap admin key seeds exactly one record; `FAKZED_ADMIN_KEY` env var supported

### Web console (`apps/ui`)

- Loading states (spinner blocks) on agent list, monitoring, sessions, and chat bootstrap
- Unified `ErrorBanner` with retry actions, `EmptyState` and `TypingDots` primitives
- Chat: typing indicator while streaming, failed sends restore the input, platform-connection placeholders
- Settings load from localStorage via lazy initializer (no flash of defaults)

### Engineering

- 315 tests, 97% coverage across both libraries

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
