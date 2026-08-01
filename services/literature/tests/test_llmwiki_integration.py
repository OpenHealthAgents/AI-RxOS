from __future__ import annotations

from unittest.mock import Mock

import pytest
import httpx

from app.services.llmwiki_integration import LLMWikiIntegrationService


@pytest.fixture
def service() -> LLMWikiIntegrationService:
    return LLMWikiIntegrationService(base_url="http://llmwiki-service", timeout_seconds=1, max_retries=2)


def test_update_knowledge_success(service: LLMWikiIntegrationService) -> None:
    payload = {
        "document_id": "doc-1",
        "title": "Example Study",
        "entities": [{"text": "aspirin"}],
        "relationships": [{"predicate": "treats"}],
        "summary": {"abstract_summary": "A short summary."},
        "evidence": [{"id": "e1", "score": 0.9}],
    }
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"status": "updated"}
    service.client.post = Mock(return_value=mock_response)

    result = service.update_knowledge(payload, tenant={"tenant_id": "tenant-1"})

    assert result["updated"] is True
    assert result["metrics"]["retries"] == 0
    assert result["status"] == "updated"


def test_update_knowledge_retries_and_succeeds(service: LLMWikiIntegrationService) -> None:
    payload = {
        "document_id": "doc-2",
        "entities": [{"text": "ibuprofen"}],
        "relationships": [{"predicate": "associated_with"}],
        "summary": {"abstract_summary": "A short summary."},
        "evidence": [],
    }

    failed = Mock()
    failed.raise_for_status.side_effect = httpx.HTTPError("boom")

    success = Mock()
    success.raise_for_status.return_value = None
    success.json.return_value = {"status": "updated"}

    call_count = {"value": 0}

    def side_effect(*args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return failed
        return success

    service.client.post = Mock(side_effect=side_effect)

    result = service.update_knowledge(payload)

    assert result["updated"] is True
    assert result["metrics"]["retries"] == 1


def test_update_knowledge_rejects_malformed_payload(service: LLMWikiIntegrationService) -> None:
    with pytest.raises(ValueError):
        service.update_knowledge({"document_id": "doc-3"})


def test_update_knowledge_raises_when_service_unavailable(service: LLMWikiIntegrationService) -> None:
    payload = {
        "document_id": "doc-4",
        "entities": [{"text": "acetaminophen"}],
        "relationships": [{"predicate": "targets"}],
        "summary": {"abstract_summary": "A summary."},
        "evidence": [],
    }
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.ConnectError("service down")
    service.client.post = Mock(return_value=mock_response)

    with pytest.raises(RuntimeError):
        service.update_knowledge(payload)
