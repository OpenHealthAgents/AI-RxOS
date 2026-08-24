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
