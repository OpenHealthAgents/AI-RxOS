from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["service"] == "workflows"
