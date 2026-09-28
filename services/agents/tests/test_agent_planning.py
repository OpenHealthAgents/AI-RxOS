from __future__ import annotations

import pytest

from app.agent_harness import (
    AgentState,
    InMemoryCheckpointStore,
    PlanExecuteNodes,
    PlanStep,
)


@pytest.mark.asyncio
async def test_plan_is_revised_after_step_failure_and_completed_work_is_preserved():
    planning_calls = 0
    executions: list[str] = []

    async def planner(state, _runtime):
        nonlocal planning_calls
        planning_calls += 1
        if planning_calls == 1:
            return [
                PlanStep(id="research", description="research"),
                PlanStep(id="write", description="write"),
            ]
        return [
            PlanStep(id="research", description="research"),
            PlanStep(id="write-v2", description="write with fallback"),
        ]

    async def executor(_state, step, _runtime):
        executions.append(step.id)
        if step.id == "write":
            raise RuntimeError("writer unavailable")
        return f"done:{step.id}"

    async def reflector(state, _runtime):
        return {"satisfied": True, "steps": len(state.data["plan"]["steps"])}

    nodes = PlanExecuteNodes(planner=planner, executor=executor, reflector=reflector)
    graph = nodes.build_graph(InMemoryCheckpointStore())
    result = await graph.run(
        object(),
        state=AgentState(run_id="plan-1", data={"original_task": "prepare report"}),
    )

    assert result.status == "completed"
    assert planning_calls == 2
    assert executions == ["research", "write", "write-v2"]
    assert result.data["plan"]["revision"] == 1
    assert result.data["plan"]["steps"][0]["status"] == "completed"
    assert result.data["plan"]["steps"][0]["result"] == "done:research"
    assert result.data["reflection"]["satisfied"] is True
