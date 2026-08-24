# agents

Part of the AI-RxOS platform. See `/architecture` at the repo root for the
full service contract this implements. Runs on port **8085**.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8085
```

## AI Platform

- **Model Registry** (`app/model_registry`): provider-neutral OpenAI, Anthropic, Google, and open-source model calls with configured timeouts, fallback models, and streaming.
- **Prompt Registry** (`app/prompt_registry`): versioned templates with strict variable interpolation and Redis/in-memory storage.
- **Tool Registry** (`app/tool_registry`): local or MCP-imported tools with input/output JSON Schema validation and handler timeouts.
- **Agent Harness** (`app/agent_harness`): typed state graphs, conditional edges, node retries, checkpoints, plan/execute/reflect nodes, and optional telemetry hooks.
- **Multi-Agent Orchestrator** (`app/multi_agent`): supervisor routing, sequential handoffs, and parallel independent agents.
- **Memory** (`app/memory`): run-local short-term memory and tenant/workspace-scoped LLM Wiki persistence through existing APIs.
- **Streaming**: register a graph with `register_streaming_graph`, then call `POST /api/v1/agents/stream` for SSE lifecycle, token, intermediate, and tool events.

Model, tool, and harness failures expose structured `AIPlatformError` fields: `code`, `operation`, `retriable`, and `details`. Logging emits structured run/node events; `telemetry_hook` is reserved for future OpenTelemetry integration.

### LangGraph Decision

**Option (b): retain the custom runtime.** This service does not currently depend on the external `langgraph` package. The local `StateGraph`/`AgentGraph` API mirrors the required LangGraph concepts: typed state, nodes, ordinary and conditional edges, checkpoint persistence, resume, and node-level retries. Keeping it avoids adding a new runtime dependency or changing the established checkpoint and streaming behavior; the public harness boundary can be migrated later if the platform adopts the package.
