import os

from fastapi.testclient import TestClient

os.environ["ENVIRONMENT"] = "test"

from app.main import app

client = TestClient(app)


def test_readiness_endpoint_includes_dependency_statuses():
    res = client.get("/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "literature"
    assert "dependencies" in body
    assert body["dependencies"]["postgresql"]["status"] == "ok"
    assert body["dependencies"]["orchestrator"]["status"] == "ok"


def test_readiness_endpoint_succeeds_when_all_dependencies_are_available(monkeypatch):
    async def fake_service_available(url: str):
        return True, "ok"

    import app.routers.health as health_module
    monkeypatch.setattr(health_module, "_service_available", fake_service_available)

    res = client.get("/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["ready"] is True
    assert body["dependencies"]["postgresql"]["status"] == "ok"
    assert body["dependencies"]["search_service"]["status"] == "ok"
    assert body["dependencies"]["kg_service"]["status"] == "ok"
    assert body["dependencies"]["orchestrator"]["status"] == "ok"


def test_readiness_endpoint_fails_when_external_services_unavailable(monkeypatch):
    async def fake_service_available(url: str):
        return False, "connection refused"

    import app.routers.health as health_module
    monkeypatch.setattr(health_module, "_service_available", fake_service_available)

    res = client.get("/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "fail"
    assert body["dependencies"]["search_service"]["status"] == "fail"
    assert body["dependencies"]["kg_service"]["status"] == "fail"
