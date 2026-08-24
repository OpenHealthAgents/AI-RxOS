from __future__ import annotations

import asyncio

import pytest

from app.agent_harness import AgentRuntime, AgentState, InMemoryCheckpointStore
from app.multi_agent import AgentOutcome, AgentSpec, Handoff, MultiAgentOrchestrator, SupervisorDecision


class EmptyRuntime:
    pass


def runtime():
    return AgentRuntime(models=EmptyRuntime(), prompts=EmptyRuntime(), tools=EmptyRuntime())


@pytest.mark.asyncio
async def test_supervisor_routes_handoff_between_agents_and_preserves_context():
    checkpoints = InMemoryCheckpointStore()
    calls: list[str] = []

    async def researcher(state, _runtime):
        calls.append("researcher")
        return AgentOutcome(
            updates={"finding": "HER2 is relevant"},
            handoff=Handoff(target_agent="writer", context={"finding": "HER2 is relevant"}, reason="draft report"),
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
    result = await orchestrator.run(runtime(), state=AgentState(run_id="handoff-1", data={"topic": "HER2"}))

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
    result = await orchestrator.run_parallel(runtime(), state=AgentState(data={"topic": "HER2"}), agent_names=["one", "two"])

    assert set(started) == {"one", "two"}
    assert result.data["one"] == 1
    assert result.data["two"] == 2