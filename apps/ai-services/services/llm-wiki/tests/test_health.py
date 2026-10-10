def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "llm-wiki"}


def test_readyz_reports_not_ready_without_a_pool(client):
    # `client` never runs lifespan (see conftest.py), so the real pool is
    # never initialized -- readyz must fail closed, not crash.
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json()["status"] == "not_ready"
