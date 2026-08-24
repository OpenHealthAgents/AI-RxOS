from __future__ import annotations

import json

import httpx
import pytest

from app.agent_harness import AgentRuntime, AgentState, InMemoryCheckpointStore, StateGraph
from app.core.security import TenantContext
from app.memory.llm_wiki import AgentMemory, LLMWikiMemoryAdapter
from app.model_registry import ModelConfig, ModelRegistry, ModelRegistryConfig
from app.model_registry.adapters import OpenAICompatibleAdapter
from app.model_registry.schemas import ModelRequest
from app.multi_agent import AgentOutcome, AgentSpec, MultiAgentOrchestrator, SupervisorDecision
from app.prompt_registry import InMemoryPromptStore, PromptRegistry
from app.routers.streaming import stream_graph
from app.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_full_platform_pipeline_streams_incrementally_and_persists_memory():
    wiki_records: dict[tuple[str, str, str], dict] = {}

    async def wiki_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = json.loads(request.content)
            tenant = payload["tenant"]
            entity = payload["entities"][0]["text"]
            wiki_records[(tenant["organization_id"], tenant["workspace_id"], entity)] = payload
            return httpx.Response(201, json={"success": True}, request=request)
        params = dict(request.url.params)
        payload = wiki_records.get((params["organization_id"], params["workspace_id"], params["slug"]))
        if payload is None:
            return httpx.Response(404, request=request)
        return httpx.Response(200, json={"current_version": 1, "latest_version": {"summary": payload["summary"]}}, request=request)

    async def model_handler(request: httpx.Request) -> httpx.Response:
        sse = "data: {\"choices\":[{\"delta\":{\"content\":\"HER2\"}}]}\n\n" \
            "data: {\"choices\":[{\"delta\":{\"content\":\" report\"}}]}\n\n" \
            "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse, request=request)

    model_client = httpx.AsyncClient(transport=httpx.MockTransport(model_handler))
    wiki_client = httpx.AsyncClient(transport=httpx.MockTransport(wiki_handler))
    model_config = ModelConfig(name="configured-model", provider="openai", base_url="https://model.test")
    model_registry = ModelRegistry(
        ModelRegistryConfig(primary_model="primary", models={"primary": model_config}),
        adapters={"primary": OpenAICompatibleAdapter(model_config, model_client)},
    )
    prompts = PromptRegistry(InMemoryPromptStore())
    await prompts.register("research", "Analyze ${topic}")
    tools = ToolRegistry()
    tools.register("uppercase", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, lambda args: args["text"].upper())
    tenant = TenantContext(organization_id="org-e2e", workspace_id="workspace-e2e")
    memory_adapter = LLMWikiMemoryAdapter("https://wiki.test", client=wiki_client)
    runtime = AgentRuntime(models=model_registry, prompts=prompts, tools=tools, tenant=tenant, memory=AgentMemory("e2e-run", tenant, memory_adapter))

    async def worker(state, dependencies):
        prompt = await dependencies.render_prompt("research", {"topic": state.data["topic"]})
        tokens = [token async for token in dependencies.stream_model(ModelRequest(messages=[{"role": "user", "content": prompt}]))]
        tool_result = await dependencies.call_tool("uppercase", {"text": "".join(tokens)})
        await dependencies.memory.persist("researcher", "last_finding", tool_result.result)
        return AgentOutcome(updates={"output": tool_result.result})

    def supervisor(state):
        return SupervisorDecision(next_agent="__end__" if state.data.get("output") else "worker")

    orchestrator = MultiAgentOrchestrator([AgentSpec("worker", worker)], supervisor, InMemoryCheckpointStore())

    async def orchestrate(state, dependencies):
        return await orchestrator.run(dependencies, state=state)

    graph = StateGraph().add_node("orchestrate", orchestrate).set_entry_point("orchestrate").compile(InMemoryCheckpointStore())
    events = [event async for event in stream_graph(graph, runtime, AgentState(run_id="e2e-run", data={"topic": "HER2"}))]
    event_types = [event.split("\n", 1)[0] for event in events]
    memory = await memory_adapter.retrieve(tenant=tenant, agent_id="researcher", key="last_finding")

    token_index = next(index for index, event in enumerate(events) if "event: token" in event)
    completed_index = next(index for index, event in enumerate(events) if "event: run_completed" in event)
    assert token_index < completed_index
    assert event_types.count("event: token") == 2
    assert memory is not None and memory["value"] == "HER2 REPORT"
    await model_client.aclose()
    await wiki_client.aclose()