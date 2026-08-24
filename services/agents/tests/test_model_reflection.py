from __future__ import annotations

import pytest

from app.agent_harness import AgentState, PlanExecuteNodes
from app.model_registry.schemas import ModelResponse


class FakeRuntime:
    async def render_prompt(self, _name, _variables):
        return "judge this"

    async def call_model(self, _request):
        return ModelResponse(model="judge", provider="openai", content='{"satisfied":false,"assessment":"missing evidence"}')


@pytest.mark.asyncio
async def test_default_reflection_uses_model_judgment():
    state = AgentState(data={"original_task": "prepare report", "plan": {"task": "prepare report", "steps": [{"id": "x", "description": "x", "status": "completed", "result": "unrelated"}]}})

    nodes = PlanExecuteNodes()
    await nodes.reflect(state, FakeRuntime())

    assert state.data["reflection"] == {"satisfied": False, "assessment": "missing evidence"}