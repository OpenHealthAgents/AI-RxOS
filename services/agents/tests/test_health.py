import asyncio

from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["service"] == "agents"


def test_tools_route_reads_live_tool_registry():
    res = client.get("/api/v1/tools")

    assert res.status_code == 200
    assert [tool["name"] for tool in res.json()["tools"]] == ["echo"]


@pytest.mark.asyncio
async def test_default_prompt_registry_is_preloaded():
    from app.main import prompt_registry

    assert await prompt_registry.store.list_versions("agent.default") == [1]


def test_invoke_async_mode_returns_job_id(monkeypatch):
    from app import main

    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def set(self, key, value, ex=None):
            self.values[key] = value

    fake_redis = FakeRedis()
    monkeypatch.setattr(main, "_redis", fake_redis)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/agents/invoke",
            json={"agentType": "default", "input": {"text": "hello"}, "async_mode": True},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["id"]


@pytest.mark.asyncio
async def test_async_job_status_reports_step_progress_and_isolates_jobs(monkeypatch):
    from app import main

    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def set(self, key, value, ex=None):
            self.values[key] = value

        async def get(self, key):
            return self.values.get(key)

    class FakeOrchestrator:
        def __init__(self):
            self.started = {"a": asyncio.Event(), "b": asyncio.Event()}
            self.release = {"a": asyncio.Event(), "b": asyncio.Event()}

        async def run(self, runtime, *, state, event_sink=None, **_kwargs):
            job_id = state.data["input"]["id"]
            await event_sink({"type": "run_started", "run_id": state.run_id})
            await event_sink({"type": "node_started", "node": f"step-{job_id}"})
            self.started[job_id].set()
            await self.release[job_id].wait()
            await event_sink({"type": "node_completed", "node": f"step-{job_id}", "next_node": "__end__"})
            await event_sink({"type": "run_completed", "run_id": state.run_id})
            return AgentState(run_id=state.run_id, data={"output": state.data["input"]["id"]}, status="completed", current_node="__end__")

    monkeypatch.setattr(main, "_redis", FakeRedis())
    fake_orchestrator = FakeOrchestrator()
    monkeypatch.setattr(main, "orchestrator", fake_orchestrator)

    first = await main.invoke_agent(main.AgentInvokeRequest(agentType="default", input={"id": "a"}, async_mode=True))
    second = await main.invoke_agent(main.AgentInvokeRequest(agentType="default", input={"id": "b"}, async_mode=True))
    await asyncio.gather(fake_orchestrator.started["a"].wait(), fake_orchestrator.started["b"].wait())
    first_status = await main.get_task(first.id)
    second_status = await main.get_task(second.id)

    assert first_status.status == "running"
    assert first_status.progress.current_step == "step-a"
    assert first_status.progress.completed_steps == 0
    assert first_status.progress.total_steps is None
    assert first_status.progress.total_steps_status == "in_progress"
    assert second_status.progress.current_step == "step-b"
    assert all("step-b" not in str(event) for event in first_status.progress.events)
    assert all("step-a" not in str(event) for event in second_status.progress.events)
    fake_orchestrator.release["a"].set()
    fake_orchestrator.release["b"].set()
