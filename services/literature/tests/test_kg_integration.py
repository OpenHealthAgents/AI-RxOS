from __future__ import annotations

from unittest.mock import Mock

import pytest
import httpx

from app.services.kg_integration import KGIntegrationService


@pytest.fixture
def service() -> KGIntegrationService:
    return KGIntegrationService(base_url="http://kg-service", timeout_seconds=1, max_retries=2)


def test_publish_graph_payload_success(service: KGIntegrationService) -> None:
    payload = {
        "document_id": "doc-1",
        "document_title": "Example",
        "entities": [{"text": "aspirin"}],
        "relationships": [{"predicate": "treats"}],
    }
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"status": "created"}
    service.client.post = Mock(return_value=mock_response)

    result = service.publish_graph_payload(payload, tenant={"tenant_id": "tenant-1"})

    assert result["published"] is True
    assert result["event_id"]
    assert result["metrics"]["retries"] == 0


def test_publish_graph_payload_retries_and_succeeds(service: KGIntegrationService) -> None:
    payload = {
        "document_id": "doc-2",
        "document_title": "Retry",
        "entities": [{"text": "ibuprofen"}],
        "relationships": [{"predicate": "associated_with"}],
    }

    failed = Mock()
    failed.raise_for_status.side_effect = httpx.HTTPError("boom")

    success = Mock()
    success.raise_for_status.return_value = None
    success.json.return_value = {"status": "created"}

    call_count = {"value": 0}

    def side_effect(*args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return failed
        return success

    service.client.post = Mock(side_effect=side_effect)

    result = service.publish_graph_payload(payload)

    assert result["published"] is True
    assert result["metrics"]["retries"] == 1


def test_publish_graph_payload_rejects_malformed_payload(service: KGIntegrationService) -> None:
    with pytest.raises(ValueError):
        service.publish_graph_payload({"document_id": "doc-3", "entities": "bad", "relationships": []})


def test_publish_graph_payload_raises_when_service_unavailable(service: KGIntegrationService) -> None:
    payload = {
        "document_id": "doc-4",
        "document_title": "Down",
        "entities": [{"text": "acetaminophen"}],
        "relationships": [{"predicate": "targets"}],
    }
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.ConnectError("service down")
    service.client.post = Mock(return_value=mock_response)

    with pytest.raises(RuntimeError):
        service.publish_graph_payload(payload)
