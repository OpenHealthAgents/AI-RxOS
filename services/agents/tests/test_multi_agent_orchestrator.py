from __future__ import annotations

import asyncio

import pytest

from app.agent_harness import AgentRuntime, AgentState, InMemoryCheckpointStore
from app.core.security import TenantContext
from app.multi_agent import (
    AgentOutcome,
    AgentSpec,
    Handoff,
    MultiAgentOrchestrator,
    SupervisorDecision,
)


class EmptyRuntime:
    pass


def runtime():
    return AgentRuntime(
        models=EmptyRuntime(), prompts=EmptyRuntime(), tools=EmptyRuntime()
    )


@pytest.mark.asyncio
async def test_registry_supports_parent_child_invocation_with_isolated_execution_context():
    orchestrator = MultiAgentOrchestrator(
        [AgentSpec("parent", lambda _state, _runtime: {"ready": True})],
        lambda _state: "__end__",
        InMemoryCheckpointStore(),
    )

    async def child(_state, runtime):
        assert runtime.execution_id is not None
        assert runtime.execution_id != "exec-parent"
        assert runtime.parent_execution_id == "exec-parent"
        assert runtime.request_id == "req-123"
        assert runtime.correlation_id == "corr-456"
        assert runtime.conversation_id == "conv-789"
        assert runtime.current_tenant is not None
        assert runtime.current_tenant.organization_id == "org-42"
        return {"child": "completed"}

    orchestrator.register_agent("child", child, allowed_parents=["parent"])

    runtime = AgentRuntime(
        models=EmptyRuntime(),
        prompts=EmptyRuntime(),
        tools=EmptyRuntime(),
        tenant=TenantContext(organization_id="org-42", user_id="user-1"),
    )
    runtime.set_agent_name("parent")
    runtime.set_execution_id("exec-parent")
    runtime.set_request_id("req-123")
    runtime.set_correlation_id("corr-456")
    runtime.set_conversation_id("conv-789")

    result = await orchestrator.invoke_agent(
        runtime,
        "child",
        state=AgentState(run_id="child-run"),
        parent_agent_name="parent",
        parent_execution_id="exec-parent",
    )

    assert result == {"child": "completed"}
    assert runtime.agent_name == "parent"
    assert runtime.execution_id == "exec-parent"
    assert runtime.parent_execution_id is None

    with pytest.raises(PermissionError):
        await orchestrator.invoke_agent(
            runtime,
            "child",
            state=AgentState(run_id="blocked-run"),
            parent_agent_name="unauthorized-parent",
            parent_execution_id="exec-other",
        )


@pytest.mark.asyncio
async def test_supervisor_routes_handoff_between_agents_and_preserves_context():
    checkpoints = InMemoryCheckpointStore()
    calls: list[str] = []

    async def researcher(state, _runtime):
        calls.append("researcher")
        return AgentOutcome(
            updates={"finding": "HER2 is relevant"},
            handoff=Handoff(
                target_agent="writer",
                context={"finding": "HER2 is relevant"},
                reason="draft report",
            ),
        )

    async def writer(state, _runtime):
        calls.append("writer")
        return {"report": f"Report: {state.data['finding']}"}

    def supervisor(state):
        handoff = state.data.get("pending_handoff")
        if handoff:
            state.data.update(handoff["context"])
            state.data.pop("pending_handoff")
            return SupervisorDecision(next_agent=handoff["target_agent"])
        if "report" in state.data:
            return SupervisorDecision(next_agent="__end__")
        return SupervisorDecision(next_agent="researcher")

    orchestrator = MultiAgentOrchestrator(
        [AgentSpec("researcher", researcher), AgentSpec("writer", writer)],
        supervisor,
        checkpoints,
    )
    result = await orchestrator.run(
        runtime(), state=AgentState(run_id="handoff-1", data={"topic": "HER2"})
    )

    assert calls == ["researcher", "writer"]
    assert result.status == "completed"
    assert result.data["report"] == "Report: HER2 is relevant"
    assert result.node_attempts["researcher"] == 1
    assert result.node_attempts["writer"] == 1


@pytest.mark.asyncio
async def test_independent_agents_run_in_parallel_and_merge_results():
    checkpoints = InMemoryCheckpointStore()
    started: list[str] = []

    async def one(_state, _runtime):
        started.append("one")
        await asyncio.sleep(0.01)
        return {"one": 1}

    async def two(_state, _runtime):
        started.append("two")
        await asyncio.sleep(0.01)
        return {"two": 2}

    orchestrator = MultiAgentOrchestrator(
        [AgentSpec("one", one), AgentSpec("two", two)],
        lambda _state: "__end__",
        checkpoints,
    )
    result = await orchestrator.run_parallel(
        runtime(), state=AgentState(data={"topic": "HER2"}), agent_names=["one", "two"]
    )

    assert set(started) == {"one", "two"}
    assert result.data["one"] == 1
    assert result.data["two"] == 2
