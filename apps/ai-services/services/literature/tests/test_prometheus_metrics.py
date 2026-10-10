import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics_prometheus_endpoint_returns_text():
    res = client.get("/metrics/prometheus")
    assert res.status_code == 200
    assert "# HELP literature_http_requests_total" in res.text
    assert "# TYPE literature_http_requests_total counter" in res.text


def test_metrics_prometheus_endpoint_uses_existing_registry():
    res = client.get("/metrics/prometheus")
    assert res.headers["content-type"].startswith("text/plain")
    assert "literature_http_request_latency_seconds" in res.text


def _metric_with_labels_exists(metrics_text: str, metric_name: str, labels: dict[str, str]) -> bool:
    label_pattern = ".*".join(f"{re.escape(k)}=\"{re.escape(v)}\"" for k, v in labels.items())
    pattern = rf"^{re.escape(metric_name)}\{{.*{label_pattern}.*\}}\s+\d+(?:\.\d+)?$"
    return re.search(pattern, metrics_text, flags=re.MULTILINE) is not None


def test_metrics_prometheus_counter_increments_after_http_request():
    client.get("/health")
    res = client.get("/metrics/prometheus")
    assert res.status_code == 200
    metrics = res.text

    assert _metric_with_labels_exists(
        metrics,
        "literature_http_requests_total",
        {"endpoint": "/health", "method": "GET", "status": "200"},
    )


def test_metrics_prometheus_histogram_records_latency():
    client.get("/health")
    res = client.get("/metrics/prometheus")
    metrics = res.text
    assert "literature_http_request_latency_seconds_count" in metrics
    assert "literature_http_request_latency_seconds_sum" in metrics
