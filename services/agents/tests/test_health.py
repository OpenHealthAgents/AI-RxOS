import asyncio

import jwt
import pytest
from fastapi.testclient import TestClient

from app.agent_harness import AgentState
from app.core.config import get_settings
from app.core.security import TenantContext
from app.main import app

client = TestClient(app)


def _auth_headers(organization_id: str = "org-test") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "user-test",
            "organization_id": organization_id,
            "workspace_id": "ws-test",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_health():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["service"] == "agents"


def test_readiness_checks_redis(monkeypatch):
    from app import main

    class HealthyRedis:
        async def ping(self):
            return True

    monkeypatch.setattr(main, "_redis", HealthyRedis())
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json()["status"] == "ready"


def test_readiness_fails_when_redis_is_unavailable(monkeypatch):
    from app import main

    class UnavailableRedis:
        async def ping(self):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(main, "_redis", UnavailableRedis())
    res = client.get("/readyz")
    assert res.status_code == 503


def test_tools_route_reads_live_tool_registry():
    res = client.get("/api/v1/tools", headers=_auth_headers())

    assert res.status_code == 200
    assert [tool["name"] for tool in res.json()["tools"]] == ["echo"]


def test_agent_routes_require_authentication():
    assert client.get("/api/v1/tools").status_code == 401
    assert client.get("/api/v1/agents/tasks/missing").status_code == 401
    assert (
        client.post(
            "/api/v1/agents/invoke",
            json={"agentType": "default", "input": {}},
        ).status_code
        == 401
    )

    def test_agent_allowlist_denies_unauthorized_agent_type():
        response = client.post(
            "/api/v1/agents/invoke",
            json={"agentType": "restricted-agent", "input": {}},
            headers=_auth_headers(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_idempotency_key_returns_existing_task_per_tenant(monkeypatch):
        from app import main
        from app.core.security import TenantContext

        class FakeRedis:
            def __init__(self):
                self.values = {}

            async def get(self, key):
                return self.values.get(key)

            async def set(self, key, value, ex=None, nx=False):
                if nx and key in self.values:
                    return False
                self.values[key] = value
                return True

        class FakeQueue:
            async def enqueue(self, task_id):
                return "message"

        monkeypatch.setattr(main, "_redis", FakeRedis())
        monkeypatch.setattr(main, "job_queue", FakeQueue())
        tenant = TenantContext(
            organization_id="org-a", workspace_id="ws-a", user_id="user-a"
        )
        request = main.AgentInvokeRequest(
            agentType="default", input={"x": 1}, async_mode=True
        )

        first = await main.invoke_agent(request, tenant, "same-key")
        second = await main.invoke_agent(request, tenant, "same-key")

        assert first.id == second.id
        assert first.status == "queued"

        other_tenant = TenantContext(
            organization_id="org-b", workspace_id="ws-a", user_id="user-b"
        )
        other = await main.invoke_agent(request, other_tenant, "same-key")
        assert other.id != first.id

        concurrent_tenant = TenantContext(
            organization_id="org-c", workspace_id="ws-a", user_id="user-c"
        )
        duplicate_a, duplicate_b = await asyncio.gather(
            main.invoke_agent(request, concurrent_tenant, "concurrent-key"),
            main.invoke_agent(request, concurrent_tenant, "concurrent-key"),
        )
        assert duplicate_a.id == duplicate_b.id


def test_task_status_is_hidden_from_another_tenant(monkeypatch):
    from app import main

    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def set(self, key, value, ex=None):
            self.values[key] = value

        async def get(self, key):
            return self.values.get(key)

    fake_redis = FakeRedis()
    monkeypatch.setattr(main, "_redis", fake_redis)
    task = main.AgentTask(
        id="tenant-task",
        agentType="default",
        status="succeeded",
        input={},
        tenant={
            "organization_id": "org-a",
            "workspace_id": "ws-a",
            "user_id": "user-a",
        },
    )
    fake_redis.values[main.TASK_KEY.format(id=task.id)] = task.model_dump_json()

    with TestClient(app) as test_client:
        response = test_client.get(
            f"/api/v1/agents/tasks/{task.id}", headers=_auth_headers("org-b")
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_rate_limit_rejects_requests_over_limit(monkeypatch):
    from fastapi import HTTPException
    from app import main

    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def incr(self, key):
            self.values[key] = self.values.get(key, 0) + 1
            return self.values[key]

        async def expire(self, key, seconds):
            return True

        async def decr(self, key):
            self.values[key] = self.values.get(key, 0) - 1
            return self.values[key]

    class FakeSettings:
        agent_rate_limit_per_minute = 1
        agent_max_concurrent_executions = 10
        agent_worker_execution_timeout_seconds = 300

    fake_redis = FakeRedis()
    monkeypatch.setattr(main, "_redis", fake_redis)
    monkeypatch.setattr(main, "settings", FakeSettings())
    tenant = TenantContext(
        organization_id="org-rate", workspace_id="ws-rate", user_id="user-rate"
    )

    assert await main._reserve_execution(tenant)
    with pytest.raises(HTTPException) as exc_info:
        await main._reserve_execution(tenant)
    assert exc_info.value.status_code == 429
    assert "rate exceeded" in exc_info.value.detail


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

    class FakeQueue:
        async def enqueue(self, task_id, **kwargs):
            return "queue-message"

    monkeypatch.setattr(main, "job_queue", FakeQueue())
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/agents/invoke",
            json={
                "agentType": "default",
                "input": {"text": "hello"},
                "async_mode": True,
            },
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
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
            await event_sink(
                {
                    "type": "node_completed",
                    "node": f"step-{job_id}",
                    "next_node": "__end__",
                }
            )
            await event_sink({"type": "run_completed", "run_id": state.run_id})
            return AgentState(
                run_id=state.run_id,
                data={"output": state.data["input"]["id"]},
                status="completed",
                current_node="__end__",
            )

    monkeypatch.setattr(main, "_redis", FakeRedis())
    fake_orchestrator = FakeOrchestrator()
    monkeypatch.setattr(main, "orchestrator", fake_orchestrator)

    class FakeQueue:
        async def enqueue(self, task_id, **kwargs):
            return "queue-message"

    monkeypatch.setattr(main, "job_queue", FakeQueue())
    tenant = TenantContext(
        organization_id="org-test", workspace_id="ws-test", user_id="user-test"
    )

    first = await main.invoke_agent(
        main.AgentInvokeRequest(
            agentType="default", input={"id": "a"}, async_mode=True
        ),
        tenant,
    )
    second = await main.invoke_agent(
        main.AgentInvokeRequest(
            agentType="default", input={"id": "b"}, async_mode=True
        ),
        tenant,
    )
    executions = asyncio.gather(main._execute_task(first), main._execute_task(second))
    await asyncio.gather(
        fake_orchestrator.started["a"].wait(), fake_orchestrator.started["b"].wait()
    )
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
    await executions
