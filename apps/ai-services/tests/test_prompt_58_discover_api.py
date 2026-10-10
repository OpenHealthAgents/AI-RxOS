from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.discover import api as discover_api
from app.opportunity_engine.discover.api import (
    ParsedFilter,
    RedisSavedSearchStore,
    SavedSearchRecord,
    get_optional_trusted_discover_identity,
    get_saved_search_store,
    get_trusted_discover_identity,
)
from app.opportunity_engine.search.models import OperatorType
from app.opportunity_engine.search.router import get_search_engine

client = TestClient(app)


class InMemorySavedSearchStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, UUID], SavedSearchRecord] = {}

    def save(self, record: SavedSearchRecord) -> None:
        key = (record.tenant_id, record.user_id, record.saved_search_id)
        self.records[key] = record

    def get(
        self,
        saved_search_id: UUID,
        *,
        tenant_id: str,
        user_id: str,
    ) -> SavedSearchRecord | None:
        return self.records.get((tenant_id, user_id, saved_search_id))


def test_discover_returns_parsed_intent_candidates_and_derived_scores() -> None:
    response = client.post("/api/discover", json={"query": "HER2 assets"})
    assert response.status_code == 200, response.text

    result = response.json()
    assert result["parsed_intent"]["target_type"] == "asset"
    assert result["parsed_intent"]["entities"]["targets"] == ["HER2"]
    assert any(item["field"] == "target" for item in result["filters"])
    assert result["ranking_status"] == "AVAILABLE_DERIVED_SEARCH"
    assert result["ml_ranking_status"] == "UNAVAILABLE"
    assert result["candidates"]
    assert all(
        candidate["scores"]["score_type"] == "DETERMINISTIC_SEARCH_HEURISTIC"
        and candidate["scores"]["ml_ranking_score"] is None
        and candidate["confidence"] is None
        and candidate["confidence_status"] == "UNKNOWN_UNCALIBRATED"
        for candidate in result["candidates"]
    )
    assert all(
        evidence.get("evidence_id") and evidence.get("source_citation")
        for candidate in result["candidates"]
        for evidence in candidate["evidence"]
    )


def test_explicit_filters_are_applied_and_response_is_deterministic() -> None:
    payload = {
        "query": "HER2 assets",
        "filters": {"target": "HER2", "stage": ["Phase II"]},
    }
    first = client.post("/api/discover", json=payload)
    second = client.post("/api/discover", json=payload)

    assert first.status_code == second.status_code == 200
    first_candidates = first.json()["candidates"]
    second_candidates = second.json()["candidates"]
    assert first_candidates == second_candidates
    assert first_candidates
    assert {
        candidate["asset_id"] for candidate in first_candidates
    } <= {"zongertinib", "poziotinib"}
    assert any(
        filter_item["field"] == "stage"
        for filter_item in first.json()["filters"]
    )


def test_empty_and_unsupported_queries_are_rejected() -> None:
    assert client.post("/api/discover", json={"query": "  "}).status_code == 422
    unsupported = client.post(
        "/api/discover",
        json={"query": "HER2 assets available for licensing"},
    )
    assert unsupported.status_code == 422
    assert "licensing_status" in unsupported.text


def test_historical_search_preserves_cutoff_without_using_current_candidates() -> None:
    response = client.post(
        "/api/discover",
        json={"query": "HER2 assets as of 2020-01-01"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["evaluation_cutoff"] == "2020-01-01"
    assert result["status"] == "UNAVAILABLE"
    assert result["ranking_status"] == "UNAVAILABLE_POINT_IN_TIME_SEARCH_DATA"
    assert result["candidates"] == []
    assert "no current data was used" in result["unknowns"][0]


def test_invalid_or_future_historical_cutoffs_are_rejected() -> None:
    invalid = client.post(
        "/api/discover",
        json={"query": "HER2 assets as of not-a-date"},
    )
    assert invalid.status_code == 422
    partial = client.post(
        "/api/discover",
        json={"query": "HER2 assets as of 2024-02"},
    )
    assert partial.status_code == 422
    future = client.post(
        "/api/discover",
        json={"query": "HER2 assets", "as_of": "2999-01-01"},
    )
    assert future.status_code == 422


def test_missing_candidate_evidence_remains_unknown() -> None:
    class SearchWithoutEvidence:
        def search(self, _request: object) -> SimpleNamespace:
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        id="asset-with-unknown-evidence",
                        title="Asset with unknown evidence",
                        score=60.0,
                        semantic_similarity=0.25,
                        match_reasons=["Semantic query relevance match"],
                        evidence=[],
                        unknowns=[],
                    )
                ]
            )

    app.dependency_overrides[get_search_engine] = lambda: SearchWithoutEvidence()
    try:
        response = client.post(
            "/api/discover",
            json={"query": "unknown evidence asset"},
        )
    finally:
        app.dependency_overrides.pop(get_search_engine, None)

    assert response.status_code == 200, response.text
    candidate = response.json()["candidates"][0]
    assert candidate["evidence"] == []
    assert candidate["evidence_status"] == "UNKNOWN"
    assert candidate["confidence"] is None
    assert "Supporting evidence is unavailable" in candidate["unknowns"][0]


def test_unmatched_query_does_not_return_baseline_candidates() -> None:
    response = client.post(
        "/api/discover",
        json={"query": "qxz-no-registered-asset-match"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["candidates"] == []


def test_nested_filters_reject_unknown_fields() -> None:
    response = client.post(
        "/api/discover",
        json={
            "query": "HER2 assets",
            "filters": {"target": "HER2", "tenant_id": "attacker"},
        },
    )
    assert response.status_code == 422


def test_saved_search_persists_structured_filters_and_enforces_owner_scope() -> None:
    store = InMemorySavedSearchStore()
    app.dependency_overrides[get_saved_search_store] = lambda: store
    app.dependency_overrides[get_optional_trusted_discover_identity] = lambda: (
        "tenant-a",
        "user-a",
    )
    app.dependency_overrides[get_trusted_discover_identity] = lambda: (
        "tenant-a",
        "user-a",
    )
    try:
        saved = client.post(
            "/api/discover",
            json={"query": "HER2 assets", "save_as": "HER2 opportunities"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["tenant_id"] == "tenant-a"
        search_id = saved.json()["saved_search_id"]
        assert search_id

        retrieved = client.get(f"/api/discover/saved-searches/{search_id}")
        assert retrieved.status_code == 200, retrieved.text
        saved_result = retrieved.json()
        assert saved_result["query"] == "HER2 assets"
        assert saved_result["tenant_id"] == "tenant-a"
        assert any(item["field"] == "target" for item in saved_result["filters"])

        app.dependency_overrides[get_optional_trusted_discover_identity] = lambda: (
            "tenant-b",
            "user-b",
        )
        app.dependency_overrides[get_trusted_discover_identity] = lambda: (
            "tenant-b",
            "user-b",
        )
        unauthorized = client.get(f"/api/discover/saved-searches/{search_id}")
        assert unauthorized.status_code == 404
    finally:
        app.dependency_overrides.pop(get_saved_search_store, None)
        app.dependency_overrides.pop(get_optional_trusted_discover_identity, None)
        app.dependency_overrides.pop(get_trusted_discover_identity, None)


def test_saved_search_requires_trusted_identity() -> None:
    response = client.post(
        "/api/discover",
        json={"query": "HER2 assets", "save_as": "restricted"},
    )
    assert response.status_code == 403


def test_redis_saved_search_store_round_trips_structured_query(monkeypatch) -> None:
    values: dict[str, str] = {}

    class RedisFake:
        def set(self, key: str, value: str) -> None:
            values[key] = value

        def get(self, key: str) -> str | None:
            return values.get(key)

    redis_fake = RedisFake()
    monkeypatch.setattr(
        discover_api.Redis,
        "from_url",
        lambda *_args, **_kwargs: redis_fake,
    )
    store = RedisSavedSearchStore()
    record = SavedSearchRecord(
        saved_search_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        tenant_id="tenant-a",
        user_id="user-a",
        name="HER2 targets",
        query="HER2 assets",
        filters=[
            ParsedFilter(
                field="target",
                operator=OperatorType.EQUALS,
                value="HER2",
                source_span="HER2",
            )
        ],
        created_at=datetime.now(timezone.utc),
    )

    store.save(record)
    restored = store.get(
        record.saved_search_id,
        tenant_id="tenant-a",
        user_id="user-a",
    )
    assert restored == record
    assert store.get(
        record.saved_search_id,
        tenant_id="tenant-b",
        user_id="user-a",
    ) is None


def test_invalid_saved_search_identifier_is_rejected() -> None:
    app.dependency_overrides[get_trusted_discover_identity] = lambda: (
        "tenant-a",
        "user-a",
    )
    try:
        response = client.get("/api/discover/saved-searches/not-a-uuid")
    finally:
        app.dependency_overrides.pop(get_trusted_discover_identity, None)
    assert response.status_code == 422
