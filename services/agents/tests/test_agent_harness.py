from __future__ import annotations

import pytest

from app.agent_harness import AgentRuntime, AgentState, InMemoryCheckpointStore, RetryPolicy, StateGraph
from app.core.security import TenantContext
from app.model_registry.schemas import ModelRequest, ModelResponse
from app.prompt_registry.registry import PromptRegistry
from app.prompt_registry.storage import InMemoryPromptStore
from app.tool_registry import ToolRegistry


class FakeModels:
    async def complete(self, request):
        return ModelResponse(model="configured-model", provider="openai", content=request.messages[0]["content"])


@pytest.mark.asyncio
async def test_single_node_run_uses_all_registries_and_checkpoints():
    prompts = PromptRegistry(InMemoryPromptStore())
    await prompts.register("agent_task", "Analyze ${topic}")
    tools = ToolRegistry()
    tools.register("uppercase", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, lambda args: args["text"].upper())
    runtime = AgentRuntime(models=FakeModels(), prompts=prompts, tools=tools)
    checkpoints = InMemoryCheckpointStore()

    async def node(state, dependencies):
        prompt = await dependencies.render_prompt("agent_task", {"topic": state.data["topic"]})
        response = await dependencies.call_model(ModelRequest(messages=[{"role": "user", "content": prompt}]))
        tool_result = await dependencies.call_tool("uppercase", {"text": response.content})
        return {"answer": tool_result.result}

    graph = StateGraph().add_node("agent", node).set_entry_point("agent").compile(checkpoints)
    result = await graph.run(runtime, state=AgentState(run_id="run-1", data={"topic": "HER2"}))

    assert result.status == "completed"
    assert result.data["answer"] == "ANALYZE HER2"
    assert result.node_attempts["agent"] == 1
    saved = await checkpoints.load("run-1")
    assert saved is not None and saved.current_node == "__end__"


@pytest.mark.asyncio
async def test_graph_auto_attaches_run_scoped_memory():
    prompts = PromptRegistry(InMemoryPromptStore())
    tools = ToolRegistry()
    runtime = AgentRuntime(models=FakeModels(), prompts=prompts, tools=tools, tenant=TenantContext(organization_id="org-a"))

    async def node(state, dependencies):
        assert dependencies.memory is not None
        assert dependencies.memory.run_id == state.run_id
        dependencies.memory.remember("run_value", state.run_id)
        return {}

    graph = StateGraph().add_node("memory", node).set_entry_point("memory").compile(InMemoryCheckpointStore())
    result = await graph.run(runtime, state=AgentState(run_id="memory-run"))

    assert result.status == "completed"
    assert runtime.memory is not None
    assert runtime.memory.run_id == "memory-run"


@pytest.mark.asyncio
async def test_node_retry_and_resume_from_failed_checkpoint():
    runtime = AgentRuntime(models=object(), prompts=object(), tools=object())
    checkpoints = InMemoryCheckpointStore()
    attempts = {"count": 0}

    async def flaky(state, _runtime):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("temporary")
        return {"ok": True}

    graph = StateGraph().add_node("flaky", flaky, retry=RetryPolicy(max_attempts=2)).set_entry_point("flaky").compile(checkpoints)
    result = await graph.run(runtime, state=AgentState(run_id="run-2"))
    assert result.data["ok"] is True
    assert result.node_attempts["flaky"] == 2