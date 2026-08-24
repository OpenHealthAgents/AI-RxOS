import json
import os
import asyncio
import uuid
from typing import Any, Literal

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.agent_harness import AgentState, InMemoryCheckpointStore, StateGraph
from app.memory.llm_wiki import create_agent_memory
from app.memory.conversation import ConversationMemoryStore
from app.model_registry import ModelConfig, ModelRegistry, ModelRegistryConfig, ModelRequest
from app.multi_agent import AgentSpec, MultiAgentOrchestrator, SupervisorDecision
from app.prompt_registry import InMemoryPromptStore, PromptRegistry, PromptTemplate
from app.routers import conversations as conversations_router
from app.routers import memory as memory_router
from app.routers import streaming as streaming_router
from app.tool_registry import ToolRegistry

settings = get_settings()
app = FastAPI(
    title="AI-RxOS Agent Orchestrator",
    description="Agent registration, invocation, tool routing, and "
    "conversation memory for the AI Orchestration context.",
    version="0.1.0",
)

_redis = redis.from_url(settings.redis_url, decode_responses=True)
TASK_KEY = "agents:task:{id}"

conversation_memory_store = ConversationMemoryStore(_redis)


def _build_model_registry() -> ModelRegistry:
    configured = settings.model_registry_json or os.getenv("MODEL_REGISTRY_JSON")
    if configured:
        registry_config = ModelRegistryConfig.from_json(configured)
    else:
        model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")
        provider = os.getenv("MODEL_PROVIDER", "openai")
        registry_config = ModelRegistryConfig(
            primary_model="default",
            models={"default": ModelConfig(name=model_name, provider=provider)},
        )
    return ModelRegistry(registry_config)


model_registry = _build_model_registry()
prompt_store = InMemoryPromptStore()
prompt_store._prompts[("agent.default", 1)] = PromptTemplate(name="agent.default", version=1, template="Answer the user's task directly and clearly.\n\nTask: ${input}")
prompt_store._prompts[("agent.plan", 1)] = PromptTemplate(name="agent.plan", version=1, template="Create an ordered execution plan for: ${task}\nPrior plan: ${feedback}")
prompt_store._prompts[("agent.reflect", 1)] = PromptTemplate(name="agent.reflect", version=1, template="Judge whether this output satisfies the task. Task: ${task}\nOutput: ${result}")
prompt_registry = PromptRegistry(prompt_store)
tool_registry = ToolRegistry()
tool_registry.register(
    "echo",
    {"type": "object", "properties": {"value": {}}, "required": ["value"]},
    lambda arguments: arguments["value"],
)


async def _default_agent(state: AgentState, runtime) -> dict[str, str]:
    messages = state.data.get("messages")
    if not messages:
        prompt = await runtime.render_prompt("agent.default", {"input": str(state.data.get("input", ""))})
        messages = [{"role": "user", "content": prompt}]
    response = await runtime.call_model(ModelRequest(messages=messages))
    return {"output": response.content}


def _default_supervisor(state: AgentState) -> SupervisorDecision:
    return SupervisorDecision(next_agent="__end__" if state.data.get("output") else "default")


orchestrator = MultiAgentOrchestrator(
    [AgentSpec("default", _default_agent)],
    _default_supervisor,
    InMemoryCheckpointStore(),
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
    .compile(InMemoryCheckpointStore())
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
    agentType: str
    status: Literal["pending", "running", "succeeded", "failed"]
    input: dict[str, Any]
    result: dict[str, Any] | None = None
    progress: AgentProgress = Field(default_factory=AgentProgress)


async def _execute_task(task: AgentTask) -> None:
    async def record_event(event: dict[str, Any]) -> None:
        if event["type"] == "node_started":
            task.progress.current_step = event.get("node")
        elif event["type"] == "node_completed":
            task.progress.completed_steps += 1
            task.progress.current_step = event.get("next_node")
        elif event["type"] in {"run_completed", "run_error"}:
            task.progress.current_step = None
        task.progress.events = [*task.progress.events[-49:], event]
        await _redis.set(TASK_KEY.format(id=task.id), task.model_dump_json(), ex=86400)

    task.status = "running"
    await _redis.set(TASK_KEY.format(id=task.id), task.model_dump_json(), ex=86400)
    try:
        result = await orchestrator.run(
            agent_runtime,
            state=AgentState(run_id=task.id, data={"input": task.input, "agent_type": task.agentType}),
            event_sink=record_event,
        )
        task.status = "succeeded"
        task.result = result.data
        task.progress.current_step = None
        task.progress.total_steps_status = "known"
        task.progress.total_steps = task.progress.completed_steps
    except Exception as exc:  # noqa: BLE001
        task.status = "failed"
        task.result = {"error": str(exc)}
        task.progress.current_step = None
    await _redis.set(TASK_KEY.format(id=task.id), task.model_dump_json(), ex=86400)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agents"}


@app.post("/api/v1/agents/invoke", response_model=AgentTask)
async def invoke_agent(req: AgentInvokeRequest) -> AgentTask:
    task = AgentTask(id=str(uuid.uuid4()), agentType=req.agentType, status="pending", input=req.input)
    if req.async_mode:
        await _redis.set(TASK_KEY.format(id=task.id), task.model_dump_json(), ex=86400)
        asyncio.create_task(_execute_task(task))
        return task
    await _execute_task(task)
    await _redis.set(TASK_KEY.format(id=task.id), task.model_dump_json(), ex=86400)
    return task


@app.get("/api/v1/agents/tasks/{task_id}", response_model=AgentTask)
async def get_task(task_id: str) -> AgentTask:
    raw = await _redis.get(TASK_KEY.format(id=task_id))
    if raw is None:
        raise HTTPException(status_code=404, detail="task not found")
    return AgentTask(**json.loads(raw))


@app.get("/api/v1/tools")
def list_tools() -> dict[str, list[dict[str, Any]]]:
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
