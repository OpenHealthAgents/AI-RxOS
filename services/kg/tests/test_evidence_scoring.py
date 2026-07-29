from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import evidence_service

client = TestClient(app)


# ---------------------------------------------------------------------------
# Pure scoring function
# ---------------------------------------------------------------------------

def test_known_source_scores_higher_than_unknown_source():
    known = evidence_service.compute_confidence(source="DrugBank", evidence=None, corroboration_count=0)
    unknown = evidence_service.compute_confidence(source="some blog", evidence=None, corroboration_count=0)
    assert known > unknown


def test_corroboration_increases_score():
    none = evidence_service.compute_confidence(source="PubMed", evidence=None, corroboration_count=0)
    some = evidence_service.compute_confidence(source="PubMed", evidence=None, corroboration_count=3)
    saturated = evidence_service.compute_confidence(source="PubMed", evidence=None, corroboration_count=50)
    assert none < some < saturated
    assert 0.0 <= saturated <= 1.0


def test_recent_evidence_scores_higher_than_old_evidence():
    recent = evidence_service.compute_confidence(source="NCBI", evidence="Confirmed in a 2025 cohort study")
    old = evidence_service.compute_confidence(source="NCBI", evidence="Confirmed in a 1995 cohort study")
    assert recent > old


def test_score_is_clamped_to_unit_interval():
    score = evidence_service.compute_confidence(source="DrugBank", evidence="2026 study", corroboration_count=999)
    assert 0.0 <= score <= 1.0


def test_missing_source_and_evidence_falls_back_to_neutral_defaults():
    score = evidence_service.compute_confidence(source=None, evidence=None, corroboration_count=0)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Wiring through GraphService.create_relationship
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    """Fakes the Neo4j session enough to exercise real service-layer logic
    (as opposed to mocking GraphService itself) so the evidence-scoring
    wiring actually runs. Dispatches on the cypher function's __name__ since
    a single test may trigger several distinct queries.py calls."""
    async def fake_execute_read(func, **kwargs):
        name = getattr(func, "__name__", "")
        if name == "get_max_active_version":
            return 1
        if name == "count_relationships_between":
            return 2
        return None

    async def fake_execute_write(func, **kwargs):
        name = getattr(func, "__name__", "")
        if name == "create_relationship":
            return {
                "id": kwargs["rel_id"],
                "from_node_id": kwargs["from_node_id"],
                "to_node_id": kwargs["to_node_id"],
                "type": kwargs["relationship_type"],
                "evidence": kwargs["evidence"],
                "confidence": kwargs["confidence"],
                "source": kwargs["source"],
                "created_at": kwargs["created_at"],
                "version": kwargs["version"],
            }
        return None

    with patch("app.database.neo4j.neo4j_manager.get_session") as mock_get:
        mock_sess = AsyncMock()
        mock_sess.execute_read = AsyncMock(side_effect=fake_execute_read)
        mock_sess.execute_write = AsyncMock(side_effect=fake_execute_write)
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=None)
        yield mock_sess


def test_create_relationship_computes_confidence_when_omitted(mock_session):
    payload = {
        "from_node_id": "a0e28f32-75d1-44bb-857e-07a82fe814e5",
        "to_node_id": "b0e28f32-75d1-44bb-857e-07a82fe814e5",
        "type": "TARGETS",
        "evidence": "Reported in a 2024 study",
        "source": "DrugBank",
    }
    res = client.post("/api/v1/graph/relationships", json=payload)
    assert res.status_code == 201
    data = res.json()
    expected = evidence_service.compute_confidence(source="DrugBank", evidence="Reported in a 2024 study", corroboration_count=2)
    assert data["confidence"] == expected


def test_create_relationship_keeps_caller_supplied_confidence(mock_session):
    payload = {
        "from_node_id": "a0e28f32-75d1-44bb-857e-07a82fe814e5",
        "to_node_id": "b0e28f32-75d1-44bb-857e-07a82fe814e5",
        "type": "TARGETS",
        "confidence": 0.42,
        "source": "DrugBank",
    }
    res = client.post("/api/v1/graph/relationships", json=payload)
    assert res.status_code == 201
    assert res.json()["confidence"] == 0.42
