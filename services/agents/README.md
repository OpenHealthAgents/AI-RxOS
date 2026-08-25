# Agents Service (`/services/agents`)

## Overview

The `agents` service is the central AI Platform component for the AI-RxOS platform, providing agent execution, multi-agent orchestration, tenant-isolated memory management, prompt versioning, tool registration, and provider-agnostic model access across port **8085**.

## LangGraph Runtime

This service uses the official `langgraph` package as the graph runtime backing the agent harness in `app/agent_harness/graph.py` while preserving the repository's existing checkpoint, security, and job execution contracts.

* **Runtime Compliance**: The harness is backed by `langgraph.graph.StateGraph`, with the repository-specific `AgentState`, `AgentRuntime`, `RedisCheckpointStore`, and worker orchestration layered on top so the public API remains stable.
* **Execution**: `AgentGraph.run()` invokes the compiled LangGraph graph with `ainvoke()`. Node adapters preserve retry policies, transition limits, tenant memory attachment, lifecycle events, and checkpoint persistence without maintaining a second graph execution loop.

The production API wiring uses `RedisCheckpointStore` and applies the
`AGENT_MAX_TRANSITIONS` budget (default `100`). Async jobs are submitted to a
Redis Streams consumer group and executed by `python -m app.jobs.worker`.

Workers reclaim pending messages after `AGENT_WORKER_RECLAIM_IDLE_SECONDS`
(default `60`) using `XAUTOCLAIM`. A per-task Redis lock prevents concurrent
execution during recovery. `AGENT_WORKER_EXECUTION_TIMEOUT_SECONDS` bounds a
job and `AGENT_WORKER_LOCK_TTL_SECONDS` bounds ownership (the default is `390`,
which exceeds the default execution plus reclaim windows). Task transitions are
durable and terminal tasks are acknowledged without re-execution. Cancellation
is requested with `POST /api/v1/agents/tasks/{task_id}/cancel` and is observed
by queued, retrying, and in-flight executions.

Worker recovery tests are separated by evidence level: `tests/test_worker_recovery.py`
is deterministic local coverage; `tests/live/test_live_worker_recovery.py` uses
the configured Redis service when `AI_RXOS_LIVE_WORKER_TESTS=1`; a full
multi-process crash test requires a deployed worker command and is not run by
default. Configure `AGENT_WORKER_RECLAIM_IDLE_SECONDS`,
`AGENT_WORKER_EXECUTION_TIMEOUT_SECONDS`, `AGENT_WORKER_LOCK_TTL_SECONDS`, and
`REDIS_OPERATION_TIMEOUT_SECONDS` in production.

### Durable Execution Payloads

Operational Redis task and checkpoint records contain metadata and references
only. Request input, intermediate state, tool data, and results are stored in
`RedisExecutionPayloadStore` under tenant/workspace-scoped keys and encrypted
with Fernet. Configure `EXECUTION_PAYLOAD_KEY` with a stable production key;
the service fails closed if the development fallback is used in production. Workers and graph
resume operations hydrate payloads only after applying the tenant/workspace
scope.

---

## Architecture Summary

### 1. Model Registry (`app/model_registry`)
Provides a provider-neutral abstraction layer over LLM providers (OpenAI, Anthropic, Google Generative Language, and self-hosted HuggingFace TGI endpoints). Supports configurable model request parameters, token streaming, per-model timeout enforcement, and automated fallback execution across ordered fallback model chains.

### 2. Prompt Registry (`app/prompt_registry`)
Manages versioned prompt templates with string variable interpolation (`Template.substitute`), auto-incrementing version assignment, and flexible storage options (`InMemoryPromptStore` and `RedisPromptStore`).

### 3. Tool Registry (`app/tool_registry`)
Handles local and remote tool registration, input and output JSON Schema validation, sync/async handler execution, execution timeouts, authorization policies, retry-mode declarations, and automatic MCP tool schema conversion.

### 4. LangGraph Agent Harness (`app/agent_harness`)
Built on the official `langgraph.graph.StateGraph` and a compatibility facade that adapts the typed `AgentState` model, node handlers, conditional routing, Redis checkpoint persistence, retries, and bounded `ainvoke()` execution. A resume entry node routes a recovered run to its persisted `current_node`; the LangGraph recursion limit bounds cyclic graphs.

### 5. Multi-Agent Orchestrator (`app/multi_agent`)
Implements supervisor-driven multi-agent routing via `MultiAgentOrchestrator`. Supports `AgentOutcome` state updates, sequential agent handoffs (`Handoff`), and concurrent parallel execution of independent agents via `run_parallel()`.

### 6. Memory Architecture (`app/memory`)
Provides a unified memory access layer via the `create_agent_memory()` factory, used consistently by both API endpoints (`app/routers/memory.py`) and active graph execution runs.
- **Short-Term & Chat Context**: `AgentMemory` handles run-scoped short-term dictionary storage, backed by Redis for tenant/workspace key indexing (`agent:memory:{org}:{workspace}:{agent_id}:{key}`). `ConversationMemoryStore` manages Redis-backed sliding window chat history (`agent:context:{conversation_id}`).
- **Long-Term Persistence**: Delegated to `LLMWikiMemoryAdapter`, compiling document summaries into external LLM Wiki pages via `/api/v1/wiki/compile` and retrieving via `/api/v1/wiki/pages`.
- **Per-Run Isolation**: `AgentRuntime` uses Python `ContextVar` instances (`_memory` and `_event_sink`) to guarantee that memory context and telemetry sinks remain strictly isolated per async execution context.

### 7. Planning & Reasoning (`app/agent_harness/planning.py`)
Provides reusable `PlanExecuteNodes` for task decomposition and execution. Generates structured `ExecutionPlan` steps, tracks step progress, triggers replanning upon step failure, and performs model-backed reflection (`reflect()`) to evaluate output satisfaction.

### 8. Streaming (`app/routers/streaming.py`)
Exposes `POST /api/v1/agents/stream`, yielding Server-Sent Events (SSE) for graph lifecycle starts, live LLM output tokens, tool call executions, tool results, and multi-agent handoff updates.

### 9. MCP Client (`app/tool_registry/mcp_client.py`)
MCP JSON-RPC 2.0 HTTP client supporting `initialize`, `tools/list`, and `tools/call`. Maintains `Mcp-Session-Id` header persistence, applies bounded timeouts and transient-only reconnects, validates protocol and SSE responses, and consumes streaming tool output into redacted metadata events. Imported tools execute through `ToolRegistry`, which enforces agent, permission, organization, and workspace authorization before every call.

### 10. Async Job Execution (`app/main.py`)
Supports asynchronous background execution by invoking `POST /api/v1/agents/invoke` with `async_mode: true`. The API stores a tenant-scoped task record and enqueues its ID on the `agents:jobs` Redis Stream. A consumer-group worker claims, executes, retries, recovers stale messages, and acknowledges jobs. `Idempotency-Key` prevents duplicate submissions within a tenant scope.

---

## Concurrency & Isolation Guarantees

The service enforces strict tenant and run isolation:
- **Thread/Task Isolation**: `AgentRuntime` utilizes Python `ContextVar`s for `_memory` and `_event_sink`. Concurrent graph runs sharing a single `AgentRuntime` instance cannot access or leak memory contexts, event listeners, or telemetry streams across tasks.
- **Tenant Isolation**: Conversation history and memory stores require explicit `TenantContext` parameters (`organization_id`, `workspace_id`), enforcing isolated Redis keys and forbidding cross-tenant data access.
- **Task Isolation**: Async task keys (`agents:task:{id}`) operate on unique UUID task IDs.

*Verification*: Dedicated concurrency tests in [`tests/test_memory_access_consistency.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_memory_access_consistency.py) verify that parallel graph runs sharing runtime instances operate without cross-talk or state leakage.

---

## API Reference

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/healthz` | `GET` | Health check endpoint returning status and service name. |
| `/api/v1/agents/invoke` | `POST` | Invokes an agent task synchronously or asynchronously (`async_mode: true`). |
| `/api/v1/agents/tasks/{task_id}` | `GET` | Polls the current status, step progress, and results of an async agent task. |
| `/api/v1/tools` | `GET` | Lists all registered tools and their input/output JSON schemas. |
| `/api/v1/agents/memory` | `POST / GET` | Stores, retrieves, or searches tenant-isolated agent memory entries. |
| `/api/v1/agents/conversations` | `POST / GET` | Appends messages to or retrieves sliding window chat history for a conversation. |
| `/api/v1/agents/stream` | `POST` | Streams live SSE events (`node_started`, `token`, `tool_call`, `run_completed`) for graph execution. |
| `/metrics` | `GET` | Exposes basic Prometheus-compatible request and error counters. |

---

## How to Run

### Installation

```bash
cd services/agents
pip install -r requirements.txt
```

### Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Connection string for Redis cache, tasks, and graph checkpoints. |
| `AGENT_MAX_TRANSITIONS` | No | `100` | Maximum graph node transitions per run. |
| `AGENT_MAX_RETRIES` | No | `3` | Maximum worker retries after a failed job. |
| `LLM_WIKI_URL` | No | `None` | Base URL for external LLM Wiki service long-term memory. |
| `OPENAI_API_KEY` | No | `None` | API key for OpenAI provider adapter. |
| `ANTHROPIC_API_KEY` | No | `None` | API key for Anthropic provider adapter. |
| `GOOGLE_API_KEY` | No | `None` | API key for Google Generative Language provider adapter. |
| `MODEL_NAME` | No | `gpt-4o-mini` | Default primary model name. |
| `MODEL_PROVIDER` | No | `openai` | Default primary model provider. |
| `ALLOWED_AGENT_TYPES` | No | `default` | Comma-separated agent allowlist. |

Provider model registry entries may omit `api_key`; the service resolves
credentials from `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or
`OPEN_SOURCE_API_KEY` according to the provider. Set
`AI_RXOS_LIVE_MODEL_TESTS=1` and the provider-specific live model variables to
run the opt-in real-provider tests under `tests/live/`. Live tests never log
request payloads or credentials.

### Running the Service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8085 --reload
```

Run the durable background worker separately in each worker process:

```bash
python -m app.jobs.worker
```

### Running Tests

Execute pytest from inside the `services/agents` directory:

```bash
python -m pytest
```

### Code Tests

Latest verified results from this directory:

| Check | Result |
| :--- | :--- |
| Full test suite | **PASS**: 91 passed, 0 failed |
| Skipped tests | **PASS**: 7 intentional opt-in live tests; no core tests skipped unexpectedly |
| Ruff | **PASS**: `ruff check app` |
| mypy | **PASS**: `mypy app --ignore-missing-imports` with no issues in 42 files |
| compileall | **PASS**: `python -m compileall -q app` |

The skipped tests require external Redis, MCP, or model-provider services and
credentials. They are documented in `TESTING.md` and should be run in staging
when those dependencies are available.

### Docker Verification

Latest verified Docker results:

| Check | Result |
| :--- | :--- |
| Fresh agents image build | **PASS**: `docker compose build --no-cache agents agents-worker` |
| Agents container | **PASS**: starts as non-root user `app`; `/healthz` returns 200 |
| Worker container | **PASS**: starts as non-root user `app` with `python -m app.jobs.worker` |
| Redis container | **PASS**: Compose health check reports `healthy` |
| Docker test suite | **PASS**: 91 passed, 7 intentional live-test skips |
| Container `pip check` | **PASS**: no broken requirements |

The test and service logs contain only the known pytest-asyncio and LangGraph
deprecation warnings; neither affects execution.

### Deployment Verification

| Check | Result |
| :--- | :--- |
| Helm lint | **PASS**: chart linted with 0 failures; only the optional icon recommendation remains |
| Helm production template | **PASS**: production values render agents and agents-worker Deployments successfully |
| Redis-up readiness | **PASS**: `/readyz` returns `{"status":"ready","service":"agents"}` |
| Redis-down readiness | **PASS**: stopping Redis makes `/readyz` return HTTP 503; readiness returns healthy after Redis recovery |

### Security Verification

| Requirement | Result |
| :--- | :--- |
| Invalid and expired JWT rejection | **PASS**: production JWT tests reject invalid issuer, audience, expiry, and signing configuration |
| Missing production secrets prevent startup | **PASS**: production settings reject development payload keys/secrets and missing issuer/audience |
| Payload remains encrypted | **PASS**: Fernet ciphertext is stored in tenant-scoped Redis keys and round-trips only through the payload store |
| Sensitive metadata is redacted | **PASS**: event and exception tests remove sensitive content and expose generic errors |
| Rate limits work | **PASS**: per-tenant request limit returns HTTP 429 when exceeded |

---

## Known Limitations

1. **MCP Session Restarts**: `MCPClient` maintains `Mcp-Session-Id` headers during active runtime connections and automatically reconnects on network drops. However, session state does not persist across service process restarts.
2. **JSON Schema Validation Subset**: Tool input/output validation (`app/tool_registry/validation.py`) enforces a practical subset of JSON Schema validation (type checking, object properties, required fields, array items) rather than the full JSON Schema Draft 2020-12 spec.
3. **Mocked Provider Integration Tests**: Unit and integration tests for model providers use local HTTP mocks (`httpx.MockTransport`). No live third-party API credential calls are executed during standard automated test runs.
4. **Prompt Injection Mitigation Boundary**: Structural role separation (placing system instructions into dedicated `system` role messages) and XML-delimited `<retrieved_context>` tags are implemented in `AgentRuntime.build_structured_messages()` to establish role boundaries for LLMs. Note that structural role separation and XML delimiting reduce but do not eliminate prompt injection risk — it is one defense-in-depth mitigation layer, not a complete solution.
5. **Worker recovery boundary**: Redis Streams retain queued and acknowledged state. A worker crash leaves an in-flight message pending; another worker can reclaim it after the idle timeout. Non-idempotent tools disable automatic job retry; tools requiring idempotency keys receive stable keys derived from tenant, run, tool, and arguments.
6. **Authorization boundary**: JWT roles and permissions are consumed when present through `AuthorizationService`; agent allowlists and tool policies remain registry/configuration based because this service has no separate Better Auth permission API.
7. **Observability boundary**: Opaque request/correlation IDs, low-cardinality
	lifecycle counters, request latency histograms, and optional OpenTelemetry
	tracing are implemented. Token usage and cost accounting are not configured.
