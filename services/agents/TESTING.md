# Test Coverage Mapping & Verification (`/services/agents`)

The agents API requires bearer JWT authentication for invocation, task polling,
tool discovery, and streaming. Tests use tokens signed with the configured test
`JWT_SECRET`; direct unit calls may bypass FastAPI dependency injection.

Coverage includes Redis Stream queue semantics, tenant-scoped idempotency,
authorization allow/deny paths, stable tool execution keys, provider retry
classification, request/correlation propagation, and tenant/workspace
conversation namespaces.
## Production Hardening Checks

The suite also verifies authenticated API access, cross-tenant task denial,
per-run tenant propagation into memory, and bounded graph execution. Static
checks are:

```bash
ruff check app
mypy app --ignore-missing-imports
python -m compileall -q app
```

## Code Tests

Latest verified results from the `services/agents` directory:

- **Full test suite:** PASS, 94 passed and 0 failed.
- **Skipped tests:** PASS, 7 intentional opt-in live tests; no core Prompt 9
	tests are skipped unexpectedly.
- **Ruff:** PASS, `ruff check app`.
- **mypy:** PASS, `mypy app --ignore-missing-imports` with no issues in 42
	source files.
- **compileall:** PASS, `python -m compileall -q app`.

The seven skips are live MCP, model-provider, and Redis worker-recovery tests.
They require external services, credentials, or a valid Fernet key and are
not failures of the deterministic test suite. Run them in staging when their
prerequisites are available.

## Docker Verification

The latest Docker verification completed successfully:

- **Fresh build:** `docker compose build --no-cache agents agents-worker` passed.
- **Agents container:** freshly recreated and running as non-root user `app`;
	`GET http://localhost:8085/healthz` returned `{"status":"ok","service":"agents"}`.
- **Worker container:** freshly recreated and running as non-root user `app`.
- **Redis:** running and healthy according to the Compose health check.
- **Docker test suite:** 94 passed, 7 intentional live-test skips.
- **Container `pip check`:** passed with `No broken requirements found`.

The container emitted only known pytest-asyncio and LangGraph deprecation
warnings. A pip cache warning is expected because the non-root runtime user
cannot write to `/nonexistent/.cache/pip`; dependency validation still passed.

## Deployment Verification

- **Helm lint:** PASS, 0 chart failures; Helm reported only the optional icon recommendation.
- **Production Helm template:** PASS, production values render agents and
	agents-worker Deployments.
- **Redis-up readiness:** PASS, `/readyz` returned HTTP 200 with
	`{"status":"ready","service":"agents"}`.
- **Redis-down readiness:** PASS, stopping Redis returned HTTP 503 from
	`/readyz`; Redis was restored and readiness returned healthy.

## Security Verification

The focused security suite passes **15 tests** and verifies:

- invalid, expired, wrong-issuer, and wrong-audience production JWTs are rejected;
- missing production payload keys, JWT secrets, issuer, or audience prevent settings startup;
- execution payloads are encrypted with Fernet and tenant-scoped in Redis;
- sensitive event and exception data is redacted;
- per-tenant request limits return HTTP 429 when exceeded.

The rate-limit assertion is covered by
`tests/test_health.py::test_agent_rate_limit_rejects_requests_over_limit`.

The current implementation uses Redis checkpoints in API startup wiring and a
default maximum of 100 graph transitions. Async jobs are persisted to the
`agents:jobs` Redis Stream and consumed by `python -m app.jobs.worker` using a
consumer group with stale-message reclaim. Automatic retries are bounded by
`AGENT_MAX_RETRIES`.

## Test Suite Result

The latest local run from this directory was:

```text
94 passed, 7 skipped, 0 failed
```

The skipped tests are opt-in live tests requiring Redis, an MCP server, or
provider credentials. They are not evidence of a failed implementation, but
they must be run in an environment containing those dependencies before
claiming full live-system verification.

Run the deterministic suite with:

```bash
python -m pytest -q
```

In PowerShell, use a backtick for multiline commands. A backslash is a path
argument, not a line-continuation character:

```powershell
python -m pytest `
	tests/test_agent_harness.py `
	tests/test_tool_registry.py `
	tests/test_payload_store.py `
	tests/test_jobs.py `
	tests/test_worker_recovery.py -v
```

Run the Redis worker recovery tests when Redis is available:

```bash
AI_RXOS_LIVE_WORKER_TESTS=1 python -m pytest tests/live/ -q
```

Run the static checks with:

```bash
ruff check app
mypy app --ignore-missing-imports
python -m compileall -q app
```

# Test Coverage Mapping & Verification (`/services/agents`)

## Requirement Test Mapping Matrix

| Prompt 9 Requirement / System Fix | Implementation File(s) | Test File(s) |
| :--- | :--- | :--- |
| **LangGraph-style Harness** | [`app/agent_harness/graph.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/graph.py)<br>[`app/agent_harness/checkpoints.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/checkpoints.py)<br>[`app/agent_harness/schemas.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/schemas.py) | [`tests/test_agent_harness.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_agent_harness.py) |
| **MCP Integration** | [`app/tool_registry/mcp_client.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/tool_registry/mcp_client.py)<br>[`app/tool_registry/registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/tool_registry/registry.py) | [`tests/test_tool_registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_tool_registry.py) |
| **Multi-Agent Orchestration** | [`app/multi_agent/orchestrator.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/multi_agent/orchestrator.py)<br>[`app/multi_agent/schemas.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/multi_agent/schemas.py) | [`tests/test_multi_agent_orchestrator.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_multi_agent_orchestrator.py) |
| **LLM Wiki Memory** | [`app/memory/llm_wiki.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/memory/llm_wiki.py)<br>[`app/routers/memory.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/routers/memory.py) | [`tests/test_llm_wiki_memory.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_llm_wiki_memory.py) |
| **Conversation Memory** | [`app/memory/conversation.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/memory/conversation.py)<br>[`app/routers/conversations.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/routers/conversations.py) | [`tests/test_prompt8_memory.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_prompt8_memory.py) |
| **Prompt Registry** | [`app/prompt_registry/registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/prompt_registry/registry.py)<br>[`app/prompt_registry/storage.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/prompt_registry/storage.py)<br>[`app/prompt_registry/schemas.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/prompt_registry/schemas.py) | [`tests/test_prompt_registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_prompt_registry.py) |
| **Tool Registry** | [`app/tool_registry/registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/tool_registry/registry.py)<br>[`app/tool_registry/validation.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/tool_registry/validation.py)<br>[`app/tool_registry/schemas.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/tool_registry/schemas.py) | [`tests/test_tool_registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_tool_registry.py) |
| **Model Registry** | [`app/model_registry/registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/model_registry/registry.py)<br>[`app/model_registry/schemas.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/model_registry/schemas.py) | [`tests/test_model_registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_model_registry.py) |
| **Streaming** | [`app/routers/streaming.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/routers/streaming.py)<br>[`app/agent_harness/runtime.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/runtime.py) | [`tests/test_streaming.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_streaming.py) |
| **Reasoning** | [`app/agent_harness/planning.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/planning.py) | [`tests/test_model_reflection.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_model_reflection.py) |
| **Planning** | [`app/agent_harness/planning.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/planning.py) | [`tests/test_agent_planning.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_agent_planning.py) |
| **Provider Adapters (OpenAI / Anthropic / Google / Open-Source)** | [`app/model_registry/adapters.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/model_registry/adapters.py) | [`tests/test_model_registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_model_registry.py) |
| **Full End-to-End Pipeline** | [`app/main.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/main.py)<br>[`app/agent_harness/graph.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/graph.py)<br>[`app/multi_agent/orchestrator.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/multi_agent/orchestrator.py) | [`tests/test_full_platform_integration.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_full_platform_integration.py) |
| **AgentRuntime Isolation (Concurrency Fix)** | [`app/agent_harness/runtime.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/runtime.py) | [`tests/test_memory_access_consistency.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_memory_access_consistency.py) |
| **Memory Access-Path Consolidation (Consolidation Fix)** | [`app/memory/llm_wiki.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/memory/llm_wiki.py)<br>[`app/routers/memory.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/routers/memory.py) | [`tests/test_memory_access_consistency.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_memory_access_consistency.py)<br>[`tests/test_llm_wiki_memory.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_llm_wiki_memory.py) |
| **Async Job Progress (Async Job Fix)** | [`app/main.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/main.py) | [`tests/test_health.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_health.py)<br>[`tests/test_prompt8_memory.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_prompt8_memory.py) |
| **MCP Session / Streaming (MCP Fix)** | [`app/tool_registry/mcp_client.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/tool_registry/mcp_client.py) | [`tests/test_tool_registry.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_tool_registry.py) |
| **Backend Degradation Gracefulness** | [`app/memory/conversation.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/memory/conversation.py)<br>[`app/memory/llm_wiki.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/memory/llm_wiki.py)<br>[`app/routers/conversations.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/routers/conversations.py) | [`tests/test_resilience_and_security.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_resilience_and_security.py) |
| **Structural Role Separation / Prompt Injection Mitigation** | [`app/agent_harness/runtime.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/agent_harness/runtime.py)<br>[`app/model_registry/adapters.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/model_registry/adapters.py)<br>[`app/main.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/app/main.py) | [`tests/test_resilience_and_security.py`](file:///c:/Users/Lenovo/Downloads/AI-RxOS/services/agents/tests/test_resilience_and_security.py) |

---


