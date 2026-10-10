from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_readiness_endpoints():
    for path in ["/health", "/healthz", "/ready", "/live"]:
        res = client.get(path)
        assert res.status_code == 200
        assert res.json()["service"] == "literature"


def test_metrics_endpoint_exposes_service_state():
    res = client.get("/metrics")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "literature"
    assert body["environment"] == "test"
    assert "parser_metrics" in body
    assert "orchestrator_metrics" in body


def test_request_id_header_is_returned():
    res = client.get("/health", headers={"x-request-id": "req-123"})
    assert res.status_code == 200
    assert res.headers["x-request-id"] == "req-123"


def test_prometheus_metrics_includes_http_request_counters():
    client.get("/health")
    res = client.get("/metrics/prometheus")
    assert res.status_code == 200
    assert "literature_http_requests_total" in res.text
    assert "endpoint=\"/health\"" in res.text
    assert "method=\"GET\"" in res.text


def test_prometheus_metrics_includes_latency_histogram():
    client.get("/health")
    res = client.get("/metrics/prometheus")
    assert "literature_http_request_latency_seconds_bucket" in res.text
    assert "literature_http_request_latency_seconds_count" in res.text


def test_http_metrics_middleware_records_error_counts_for_not_found_requests():
    res = client.get("/not-found")
    assert res.status_code == 404

    metrics = client.get("/metrics/prometheus").text
    assert "literature_http_requests_total" in metrics
    assert "literature_http_request_errors_total" in metrics
    assert "literature_http_request_latency_seconds_count" in metrics
    assert "endpoint=\"/not-found\"" in metrics
    assert "method=\"GET\"" in metrics
    assert "status=\"404\"" in metrics
