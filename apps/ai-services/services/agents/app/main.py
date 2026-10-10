import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, cast

import redis.asyncio as redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.agent_harness import AgentState, RedisCheckpointStore, StateGraph
from app.core.config import get_settings
from app.core.observability import (
    configure_tracing,
    get_context,
    inject_trace_context,
    new_context,
    set_context,
    span,
)
from app.core.observability import (
    metrics as metrics_registry,
)
from app.core.security import AuthorizationService, TenantContext, get_tenant_context
from app.jobs import RedisJobQueue
from app.jobs.state import transition
from app.memory.conversation import ConversationMemoryStore
from app.model_registry import (
    ModelConfig,
    ModelRegistry,
    ModelRegistryConfig,
    ModelRequest,
)
from app.model_registry.schemas import ProviderName
from app.multi_agent import AgentSpec, MultiAgentOrchestrator, SupervisorDecision
from app.prompt_registry import InMemoryPromptStore, PromptRegistry, PromptTemplate
from app.routers import conversations as conversations_router
from app.routers import memory as memory_router
from app.routers import streaming as streaming_router
from app.security.payloads import RedisExecutionPayloadStore, tenant_scope
from app.security.redaction import redact_event, sanitize_exception
from app.tool_registry import ToolRegistry

settings = get_settings()
configure_tracing(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
app = FastAPI(
    title="AI-RxOS Agent Orchestrator",
    description="Agent registration, invocation, tool routing, and "
    "conversation memory for the AI Orchestration context.",
    version="0.1.0",
)

_redis = redis.from_url(
    settings.redis_url,
    password=settings.redis_password,
    decode_responses=True,
    socket_timeout=settings.redis_operation_timeout_seconds,
    socket_connect_timeout=settings.redis_operation_timeout_seconds,
)
TASK_KEY = "agents:task:{id}"
IDEMPOTENCY_KEY = "agents:idempotency:{scope}:{key}"
job_queue = RedisJobQueue(
    _redis, stream=settings.agent_job_stream, group=settings.agent_job_group
)
execution_payloads = RedisExecutionPayloadStore(
    _redis,
    key=settings.execution_payload_key,
    prefix="agents:task-payloads",
    ttl_seconds=settings.execution_payload_ttl,
)


def _task_payload_store() -> RedisExecutionPayloadStore:
    if execution_payloads.client is _redis:
        return execution_payloads
    return RedisExecutionPayloadStore(
        _redis,
        key=settings.execution_payload_key,
        prefix="agents:task-payloads",
        ttl_seconds=settings.execution_payload_ttl,
    )

conversation_memory_store = ConversationMemoryStore(_redis)
tenant_dependency = Depends(get_tenant_context)


def _build_model_registry() -> ModelRegistry:
    configured = settings.model_registry_json or os.getenv("MODEL_REGISTRY_JSON")
    if configured:
        registry_config = ModelRegistryConfig.from_json(configured)
    else:
        model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")
        provider = os.getenv("MODEL_PROVIDER", "openai")
        registry_config = ModelRegistryConfig(
            primary_model="default",
            models={
                "default": ModelConfig(
                    name=model_name, provider=cast(ProviderName, provider)
                )
            },
        )
    env_keys = {
        "openai": os.getenv("OPENAI_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "google": os.getenv("GOOGLE_API_KEY"),
        "open_source": os.getenv("OPEN_SOURCE_API_KEY"),
    }
    registry_config.models = {
        name: model.model_copy(
            update={"api_key": model.api_key or env_keys[model.provider]}
        )
        for name, model in registry_config.models.items()
    }
    return ModelRegistry(registry_config)


model_registry = _build_model_registry()
prompt_store = InMemoryPromptStore()
prompt_store._prompts[("agent.default", 1)] = PromptTemplate(
    name="agent.default",
    version=1,
    template="Answer the user's task directly and clearly.\n\nTask: ${input}",
)
prompt_store._prompts[("agent.plan", 1)] = PromptTemplate(
    name="agent.plan",
    version=1,
    template="Create an ordered execution plan for: ${task}\nPrior plan: ${feedback}",
)
prompt_store._prompts[("agent.reflect", 1)] = PromptTemplate(
    name="agent.reflect",
    version=1,
    template="Judge whether this output satisfies the task. Task: ${task}\nOutput: ${result}",
)
prompt_registry = PromptRegistry(prompt_store)
tool_registry = ToolRegistry()
tool_registry.register(
    "echo",
    {"type": "object", "properties": {"value": {}}, "required": ["value"]},
    lambda arguments: arguments["value"],
    allowed_agents={"default"},
)
allowed_agent_types = frozenset(
    item.strip() for item in settings.allowed_agent_types.split(",") if item.strip()
)
authorization_service = AuthorizationService()


async def _default_agent(state: AgentState, runtime) -> dict[str, str]:
    messages = state.data.get("messages")
    if not messages:
        system_instruction = "Answer the user's task directly and clearly."
        user_input = (
            str(state.data.get("input", ""))
            if state.data.get("input") is not None
            else None
        )
        retrieved_data = state.data.get("retrieved_context")
        messages = runtime.build_structured_messages(
            system_instruction=system_instruction,
            user_input=user_input,
            retrieved_context=retrieved_data,
        )
    response = await runtime.call_model(ModelRequest(messages=messages))
    return {"output": response.content}


def _default_supervisor(state: AgentState) -> SupervisorDecision:
    return SupervisorDecision(
        next_agent="__end__" if state.data.get("output") else "default"
    )


orchestrator = MultiAgentOrchestrator(
    [AgentSpec("default", _default_agent)],
    _default_supervisor,
    RedisCheckpointStore(_redis),
)
agent_runtime = __import__("app.agent_harness", fromlist=["AgentRuntime"]).AgentRuntime(
    models=model_registry,
    prompts=prompt_registry,
    tools=tool_registry,
)


async def _orchestrator_node(state: AgentState, runtime) -> AgentState:
    return await orchestrator.run(runtime, state=state)


streaming_graph = (
    StateGraph()
    .add_node("orchestrator", _orchestrator_node)
    .set_entry_point("orchestrator")
    .compile(
        RedisCheckpointStore(_redis),
        max_transitions=settings.agent_max_transitions,
        max_execution_seconds=settings.agent_worker_execution_timeout_seconds,
    )
)
streaming_router.register_streaming_graph("default", streaming_graph, agent_runtime)

app.include_router(memory_router.router)
app.include_router(conversations_router.router)
app.include_router(streaming_router.router)


class AgentInvokeRequest(BaseModel):
    agentType: str
    input: dict[str, Any]
    tools: list[str] = []
    async_mode: bool = False


class AgentProgress(BaseModel):
    current_step: str | None = None
    completed_steps: int = 0
    total_steps: int | None = None
    total_steps_status: Literal["known", "in_progress"] = "in_progress"
    events: list[dict[str, Any]] = []


class AgentTask(BaseModel):
    id: str
    job_type: str = "agent.invoke"
    agentType: str
    status: Literal["pending", "queued", "running", "retrying", "succeeded", "failed", "dead_letter", "cancelled"]
    input: dict[str, Any]
    result: dict[str, Any] | None = None
    progress: AgentProgress = Field(default_factory=AgentProgress)
    tenant: dict[str, str] = Field(default_factory=dict)
    retry_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    idempotency_key: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    retry_allowed: bool = True
    trace_context: dict[str, str] = Field(default_factory=dict)
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    worker_id: str | None = None
    cancel_requested: bool = False


async def _persist_task(task: AgentTask) -> None:
    tenant_id, workspace_id = tenant_scope(task.tenant)
    store = _task_payload_store()
    await store.put(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        payload_id=task.id,
        payload={"input": task.input, "result": task.result},
    )
    metadata = task.model_dump(mode="json", exclude={"input", "result", "idempotency_key", "trace_context"})
    metadata.update(
        {
            "payload_reference": task.id,
            "checkpoint_reference": task.id,
            "error_category": "internal" if task.error else None,
        }
    )
    await _redis.set(
        TASK_KEY.format(id=task.id),
        json.dumps(metadata, separators=(",", ":")),
        ex=settings.metadata_ttl,
    )


def _execution_scope(tenant: TenantContext) -> str:
    return f"{tenant.organization_id or '_none'}:{tenant.workspace_id or '_shared'}:{tenant.user_id or '_none'}"


async def _reserve_execution(tenant: TenantContext) -> str | None:
    increment = getattr(_redis, "incr", None)
    if increment is None:
        return None
    scope = _execution_scope(tenant)
    rate_key = f"agents:rate:{scope}"
    rate_count = await increment(rate_key)
    if rate_count == 1:
        await _redis.expire(rate_key, 60)
    if rate_count > settings.agent_rate_limit_per_minute:
        await _redis.decr(rate_key)
        raise HTTPException(status_code=429, detail="agent request rate exceeded")
    concurrent_key = f"agents:concurrent:{scope}"
    concurrent_count = await increment(concurrent_key)
    if concurrent_count == 1:
        await _redis.expire(concurrent_key, int(settings.agent_worker_execution_timeout_seconds) + 60)
    if concurrent_count > settings.agent_max_concurrent_executions:
        await _redis.decr(concurrent_key)
        raise HTTPException(status_code=429, detail="agent concurrency limit exceeded")
    return concurrent_key


async def _release_execution(key: str | None) -> None:
    if key is not None:
        await _redis.decr(key)


async def _load_task(raw: str) -> AgentTask:
    metadata = json.loads(raw)
    if "payload_reference" not in metadata:
        return AgentTask.model_validate(metadata)
    tenant_id, workspace_id = tenant_scope(metadata.get("tenant", {}))
    payload = await _task_payload_store().get(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        payload_id=metadata["payload_reference"],
    )
    metadata["input"] = (payload or {}).get("input", {})
    metadata["result"] = (payload or {}).get("result")
    return AgentTask.model_validate(metadata)


async def _execute_task(task: AgentTask) -> None:
    set_context(new_context(task.request_id, task.correlation_id))

    async def record_event(event: dict[str, Any]) -> None:
        current = await _redis.get(TASK_KEY.format(id=task.id))
        if current:
            persisted = await _load_task(current)
            if persisted.cancel_requested:
                task.cancel_requested = True
                raise asyncio.CancelledError
        if (
            event.get("type") == "tool_call"
            and event.get("retry_mode") == "non_idempotent"
        ):
            task.retry_allowed = False
        if event["type"] == "node_started":
            task.progress.current_step = event.get("node")
        elif event["type"] == "node_completed":
            task.progress.completed_steps += 1
            task.progress.current_step = event.get("next_node")
        elif event["type"] in {"run_completed", "run_error"}:
            task.progress.current_step = None
        task.progress.events = [*task.progress.events[-49:], event]
        await _persist_task(task)

    if task.status != "running":
        transition(task, "running")
    task.started_at = task.started_at or datetime.now(timezone.utc)
    task.progress.events = [
        *task.progress.events[-49:],
        redact_event(
            {
                "type": "job_started",
                "task_id": task.id,
                "execution_id": task.execution_id,
                "worker_id": task.worker_id,
                "status": task.status,
            }
        ),
    ]
    await _persist_task(task)
    try:
        checkpoint_store = RedisCheckpointStore(_redis)
        checkpoint = await checkpoint_store.load(
            task.id,
            tenant=TenantContext(
                organization_id=task.tenant.get("organization_id"),
                workspace_id=task.tenant.get("workspace_id"),
                project_id=task.tenant.get("project_id"),
                user_id=task.tenant.get("user_id"),
            ),
        )
        result = await orchestrator.run(
            agent_runtime,
            state=AgentState(
                run_id=task.id,
                data={
                    "input": task.input,
                    "agent_type": task.agentType,
                    "tenant": task.tenant,
                    "execution_id": task.execution_id,
                },
            ),
            event_sink=record_event,
            resume_run_id=task.id if checkpoint is not None else None,
        )
        transition(task, "succeeded")
        task.result = result.data
        task.completed_at = datetime.now(timezone.utc)
        task.progress.current_step = None
        task.progress.total_steps_status = "known"
        task.progress.total_steps = task.progress.completed_steps
    except Exception as exc:  # noqa: BLE001
        if task.status != "failed":
            transition(task, "failed")
        safe_error = sanitize_exception(exc)
        task.result = {"error": safe_error["error"]}
        task.error = safe_error["error"]
        task.completed_at = datetime.now(timezone.utc)
        task.progress.current_step = None
    except asyncio.CancelledError:
        if not task.cancel_requested:
            raise
        if task.status != "cancelled":
            transition(task, "cancelled")
        task.completed_at = datetime.now(timezone.utc)
        task.progress.current_step = None
    await _persist_task(task)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agents"}


@app.get("/readyz")
async def readiness() -> dict[str, str]:
    try:
        await asyncio.wait_for(
            _redis.ping(), timeout=settings.redis_operation_timeout_seconds
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="service not ready") from exc
    return {"status": "ready", "service": "agents"}


_request_count = 0
_request_errors = 0
_event_counts: dict[str, int] = {}


def observe_agent_event(event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if isinstance(event_type, str):
        _event_counts[event_type] = _event_counts.get(event_type, 0) + 1


agent_runtime.telemetry_hook = observe_agent_event


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    global _request_count, _request_errors
    _request_count += 1
    context = new_context(
        request.headers.get("X-Request-ID"), request.headers.get("X-Correlation-ID")
    )
    set_context(context)
    started = time.perf_counter()
    with span(
        "http.request",
        request_id=context.request_id,
        correlation_id=context.correlation_id,
    ):
        response = await call_next(request)
    response.headers["X-Request-ID"] = context.request_id
    response.headers["X-Correlation-ID"] = context.correlation_id
    if response.status_code >= 500:
        _request_errors += 1
    metrics_registry.inc("agent_requests_total", status=str(response.status_code))
    if response.status_code >= 500:
        metrics_registry.inc(
            "agent_requests_failed_total", status=str(response.status_code)
        )
    metrics_registry.observe(
        "agent_request_duration_seconds",
        time.perf_counter() - started,
        status=str(response.status_code),
    )
    return response


@app.get("/metrics")
def metrics() -> str:
    return (
        "# HELP agents_http_requests_total Total HTTP requests received.\n"
        "# TYPE agents_http_requests_total counter\n"
        f"agents_http_requests_total {_request_count}\n"
        "# HELP agents_http_errors_total Total HTTP 5xx responses.\n"
        "# TYPE agents_http_errors_total counter\n"
        f"agents_http_errors_total {_request_errors}\n"
        + metrics_registry.render()
        + "".join(
            f"# TYPE agents_{event_type}_total counter\n"
            f"agents_{event_type}_total {count}\n"
            for event_type, count in sorted(_event_counts.items())
        )
    )


@app.post(
    "/api/v1/agents/invoke",
    response_model=AgentTask,
    response_model_exclude={"tenant", "idempotency_key", "trace_context"},
)
async def invoke_agent(
    req: AgentInvokeRequest,
    tenant: TenantContext = tenant_dependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AgentTask:
    if not isinstance(tenant, TenantContext):
        tenant = TenantContext()
    if not isinstance(idempotency_key, str):
        idempotency_key = None
    if not authorization_service.can_execute_agent(
        tenant, req.agentType, allowed_agent_types
    ):
        raise HTTPException(status_code=403, detail="agent not authorized")
    task = AgentTask(
        id=str(uuid.uuid4()),
        agentType=req.agentType,
        status="queued" if req.async_mode else "pending",
        input=req.input,
        tenant=tenant.as_dict(),
        idempotency_key=idempotency_key,
        request_id=(context.request_id if (context := get_context()) else None),
        correlation_id=(context.correlation_id if context else None),
        trace_context=inject_trace_context(),
    )
    if req.async_mode:
        task.progress.events = [
            redact_event(
                {
                    "type": "job_queued",
                    "task_id": task.id,
                    "execution_id": task.execution_id,
                    "status": task.status,
                }
            )
        ]
    metrics_registry.inc(
        "agent_jobs_total", agent_type=req.agentType, status=task.status
    )
    if idempotency_key:
        scope = f"{tenant.organization_id or '_none'}:{tenant.workspace_id or '_shared'}:{tenant.user_id or '_none'}"
        idempotency_redis_key = IDEMPOTENCY_KEY.format(scope=scope, key=idempotency_key)
        await _persist_task(task)
        task_payload = await _redis.get(TASK_KEY.format(id=task.id))
        claimed = await _redis.set(
            idempotency_redis_key,
            task_payload,
            ex=settings.idempotency_ttl,
            nx=True,
        )
        if not claimed:
            existing_task = await _redis.get(idempotency_redis_key)
            if not existing_task:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return await _load_task(existing_task)
    if len(json.dumps(req.input, separators=(",", ":"))) > settings.agent_max_input_bytes:
        raise HTTPException(status_code=413, detail="agent input is too large")
    execution_slot = await _reserve_execution(tenant)
    if req.async_mode:
        task.status = "queued"
        await _persist_task(task)
        await job_queue.enqueue(
            task.id,
            request_id=task.request_id,
            correlation_id=task.correlation_id,
        )
        return task
    try:
        await _execute_task(task)
        await _persist_task(task)
    finally:
        await _release_execution(execution_slot)
    if idempotency_key:
        current_metadata = await _redis.get(TASK_KEY.format(id=task.id))
        await _redis.set(
            idempotency_redis_key, current_metadata, ex=settings.idempotency_ttl
        )
    return task


@app.get(
    "/api/v1/agents/tasks/{task_id}",
    response_model=AgentTask,
    response_model_exclude={"tenant", "idempotency_key", "trace_context"},
)
async def get_task(
    task_id: str,
    tenant: TenantContext = tenant_dependency,
) -> AgentTask:
    raw = await _redis.get(TASK_KEY.format(id=task_id))
    if raw is None:
        raise HTTPException(status_code=404, detail="task not found")
    task = await _load_task(raw)
    if isinstance(tenant, TenantContext) and task.tenant != tenant.as_dict():
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.post(
    "/api/v1/agents/tasks/{task_id}/cancel",
    response_model=AgentTask,
    response_model_exclude={"tenant", "idempotency_key", "trace_context"},
)
async def cancel_task(
    task_id: str,
    tenant: TenantContext = tenant_dependency,
) -> AgentTask:
    raw = await _redis.get(TASK_KEY.format(id=task_id))
    if raw is None:
        raise HTTPException(status_code=404, detail="task not found")
    task = await _load_task(raw)
    if task.tenant != tenant.as_dict():
        raise HTTPException(status_code=404, detail="task not found")
    if task.status in {"succeeded", "failed", "cancelled"}:
        return task
    task.cancel_requested = True
    if task.status in {"pending", "queued", "retrying"}:
        transition(task, "cancelled")
    await _persist_task(task)
    return task


@app.post(
    "/api/v1/agents/tasks/{task_id}/replay",
    response_model=AgentTask,
    response_model_exclude={"tenant", "idempotency_key", "trace_context"},
)
async def replay_dead_letter_task(
    task_id: str,
    tenant: TenantContext = tenant_dependency,
) -> AgentTask:
    raw = await _redis.get(TASK_KEY.format(id=task_id))
    if raw is None:
        raise HTTPException(status_code=404, detail="task not found")
    task = await _load_task(raw)
    if not authorization_service.can_replay_job(tenant, task.tenant):
        raise HTTPException(status_code=404, detail="task not found")
    if task.status in {"queued", "running", "retrying", "succeeded"}:
        return task
    if task.status != "dead_letter":
        raise HTTPException(status_code=409, detail="task is not replayable")
    transition(task, "queued")
    task.cancel_requested = False
    task.progress.events = [
        *task.progress.events[-49:],
        redact_event(
            {
                "type": "job_queued",
                "task_id": task.id,
                "execution_id": task.execution_id,
                "status": task.status,
            }
        ),
    ]
    await _persist_task(task)
    await job_queue.enqueue(task.id)
    return task


@app.get("/api/v1/tools")
def list_tools(
    _tenant: TenantContext = tenant_dependency,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "source": tool.source,
            }
            for tool in tool_registry.list_tools()
        ]
    }
