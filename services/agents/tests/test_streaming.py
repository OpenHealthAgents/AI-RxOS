from __future__ import annotations

import asyncio

import jwt
import pytest
from fastapi.testclient import TestClient

from app.agent_harness import (
    AgentRuntime,
    AgentState,
    InMemoryCheckpointStore,
    StateGraph,
)
from app.core.config import get_settings
from app.core.security import TenantContext
from app.main import app
from app.memory.llm_wiki import AgentMemory
from app.multi_agent import (
    AgentOutcome,
    AgentSpec,
    Handoff,
    MultiAgentOrchestrator,
    SupervisorDecision,
)
from app.routers import streaming


class EmptyRuntime:
    pass


def _auth_headers() -> dict[str, str]:
    token = jwt.encode(
        {"sub": "user-test", "organization_id": "org-test", "workspace_id": "ws-test"},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_stream_graph_emits_incremental_lifecycle_events():
    async def node(state, runtime):
        await runtime.emit({"type": "intermediate_step", "step": "working"})
        await asyncio.sleep(0.01)
        return {"answer": "done"}

    graph = (
        StateGraph()
        .add_node("work", node)
        .set_entry_point("work")
        .compile(InMemoryCheckpointStore())
    )
    runtime = AgentRuntime(
        models=EmptyRuntime(), prompts=EmptyRuntime(), tools=EmptyRuntime()
    )
    events = []
    async for item in streaming.stream_graph(
        graph, runtime, AgentState(data={"input": "x"})
    ):
        events.append(item)

    assert "event: run_started" in events[0]
    assert any("intermediate_step" in item for item in events)
    assert any("event: node_completed" in item for item in events)
    assert "event: run_completed" in events[-1]


def test_stream_endpoint_returns_sse_for_registered_graph():
    async def node(state, _runtime):
        return {"answer": "ok"}

    graph = (
        StateGraph()
        .add_node("work", node)
        .set_entry_point("work")
        .compile(InMemoryCheckpointStore())
    )
    runtime = AgentRuntime(
        models=EmptyRuntime(), prompts=EmptyRuntime(), tools=EmptyRuntime()
    )
    streaming.register_streaming_graph("test", graph, runtime)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agents/stream",
            json={"graph": "test", "data": {"input": "x"}},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: node_started" in response.text
    assert "event: run_completed" in response.text


def test_multi_agent_handoff_streams_over_http():
    async def researcher(state, _runtime):
        return AgentOutcome(
            updates={"finding": "HER2 finding"},
            handoff=Handoff(target_agent="writer", context={"finding": "HER2 finding"}),
        )

    async def writer(state, _runtime):
        return {"output": f"written: {state.data['finding']}"}

    def supervisor(state):
        handoff = state.data.get("pending_handoff")
        if handoff:
            state.data.update(handoff["context"])
            state.data.pop("pending_handoff")
            return SupervisorDecision(next_agent=handoff["target_agent"])
        return SupervisorDecision(
            next_agent="__end__" if state.data.get("output") else "researcher"
        )

    orchestrator = MultiAgentOrchestrator(
        [AgentSpec("researcher", researcher), AgentSpec("writer", writer)],
        supervisor,
        InMemoryCheckpointStore(),
    )

    async def orchestrate(state, dependencies):
        return await orchestrator.run(dependencies, state=state)

    graph = (
        StateGraph()
        .add_node("orchestrate", orchestrate)
        .set_entry_point("orchestrate")
        .compile(InMemoryCheckpointStore())
    )
    runtime = AgentRuntime(
        models=EmptyRuntime(), prompts=EmptyRuntime(), tools=EmptyRuntime()
    )
    streaming.register_streaming_graph("multi-agent-handoff", graph, runtime)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agents/stream",
            json={"graph": "multi-agent-handoff", "data": {"topic": "HER2"}},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.text.count("event: node_started") >= 5
    assert '"node":"researcher"' in response.text
    assert '"node":"writer"' in response.text
    assert "event: run_completed" in response.text


@pytest.mark.asyncio
async def test_concurrent_streams_isolate_memory_and_events_by_run():
    async def node(state, runtime):
        runtime.memory.remember("run_value", state.run_id)
        await asyncio.sleep(0.01)
        assert runtime.memory.recall("run_value") == state.run_id
        await runtime.emit(
            {
                "type": "memory_snapshot",
                "run_id": state.run_id,
                "value": runtime.memory.recall("run_value"),
            }
        )
        return {"output": state.run_id}

    graph = (
        StateGraph()
        .add_node("work", node)
        .set_entry_point("work")
        .compile(InMemoryCheckpointStore())
    )
    runtime = AgentRuntime(
        models=EmptyRuntime(), prompts=EmptyRuntime(), tools=EmptyRuntime()
    )

    async def collect(run_id):
        return [
            event
            async for event in streaming.stream_graph(
                graph, runtime, AgentState(run_id=run_id)
            )
        ]

    first, second = await asyncio.gather(collect("run-a"), collect("run-b"))

    assert all('"run_id":"run-b"' not in event for event in first)
    assert all('"run_id":"run-a"' not in event for event in second)
    assert any('"run_id":"run-a"' in event for event in first)
    assert any('"run_id":"run-b"' in event for event in second)


@pytest.mark.asyncio
async def test_shared_constructor_objects_and_duplicate_run_ids_are_isolated():
    shared_memory = AgentMemory("shared", TenantContext(organization_id="org-a"))
    shared_events = []
    observed_owners = []

    async def shared_sink(event):
        shared_events.append(event)

    async def node(state, runtime):
        runtime.memory.remember("owner", state.data["owner"])
        await asyncio.sleep(0.01)
        observed_owners.append(
            (state.data["owner"], runtime.memory.recall("owner"))
        )
        assert runtime.memory.recall("owner") == state.data["owner"]
        await runtime.emit({"type": "owned", "owner": runtime.memory.recall("owner")})
        return {}

    graph = (
        StateGraph()
        .add_node("work", node)
        .set_entry_point("work")
        .compile(InMemoryCheckpointStore())
    )
    runtime = AgentRuntime(
        models=EmptyRuntime(),
        prompts=EmptyRuntime(),
        tools=EmptyRuntime(),
        memory=shared_memory,
        event_sink=shared_sink,
    )

    async def collect(owner):
        return [
            event
            async for event in streaming.stream_graph(
                graph, runtime, AgentState(run_id="same-run", data={"owner": owner})
            )
        ]

    first, second = await asyncio.gather(collect("first"), collect("second"))

    assert any('"type":"owned"' in event for event in first)
    assert any('"type":"owned"' in event for event in second)
    assert all('"owner"' not in event for event in first + second)
    assert set(observed_owners) == {("first", "first"), ("second", "second")}
    assert shared_memory.recall("owner") is None
    assert shared_events == []
