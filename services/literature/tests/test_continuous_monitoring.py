from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_tenant_context
from app.database.postgres import PostgresManager
from app.knowledge.models import TenantContext
from app.main import app
from app.database import postgres as postgres_module
from app.monitoring.change_detection import (
    changed_material_fields,
    material_hash,
    material_payload,
    monitoring_event_id,
    source_category,
)


@pytest.mark.parametrize(
    ("source", "category"),
    [
        ("pubmed", "publications"),
        ("clinicaltrials", "clinical_trials"),
        ("regulatory", "regulatory"),
        ("patent", "patents"),
    ],
)
def test_only_wired_ingestion_domains_are_reported(source: str, category: str):
    assert source_category(source) == category


@pytest.mark.parametrize(
    ("source", "category"),
    [
        ("company_events", "company_events"),
        ("licensing", "licensing"),
        ("competitors", "competition"),
        ("resistance", "resistance"),
        ("cns", "cns"),
    ],
)
def test_additional_monitoring_domains_are_supported(source: str, category: str):
    assert source_category(source) == category


def test_pubmed_material_hash_ignores_retrieval_metadata():
    first = {
        "pmid": "123",
        "title": "Study",
        "abstract": "Observed result",
        "publication_date": "2025-01-01",
        "metadata": {
            "retrieved_at": "2026-01-01T00:00:00Z",
            "query": "asset A",
            "raw_xml": "<article>version 1</article>",
        },
    }
    second = {
        **first,
        "metadata": {
            "retrieved_at": "2026-02-01T00:00:00Z",
            "query": "asset A",
            "raw_xml": "<article>version 1</article>",
        },
    }
    assert material_hash(material_payload("pubmed", first)) == material_hash(
        material_payload("pubmed", second)
    )


def test_pubmed_material_hash_tracks_content_and_derived_evidence_inputs():
    first = {"title": "Study", "abstract": "Original result"}
    edited = {"title": "Study", "abstract": "Corrected result"}
    assert material_hash(material_payload("pubmed", first)) != material_hash(
        material_payload("pubmed", edited)
    )
    assert material_hash(
        material_payload(
            "pubmed", first, extracted_entities=[{"text": "Asset A", "type": "drug"}]
        )
    ) != material_hash(material_payload("pubmed", first))


def test_clinical_trial_hashes_source_observation_not_request_metadata():
    original = {
        "raw_payload": {
            "protocolSection": {"statusModule": {"overallStatus": "RECRUITING"}}
        },
        "metadata": {"query": "asset A", "retrieved_at": "2026-01-01T00:00:00Z"},
    }
    retrieved_again = {
        **original,
        "metadata": {"query": "asset B", "retrieved_at": "2026-02-01T00:00:00Z"},
    }
    corrected = {
        "raw_payload": {
            "protocolSection": {"statusModule": {"overallStatus": "COMPLETED"}}
        },
        "metadata": original["metadata"],
    }
    assert material_hash(material_payload("clinicaltrials", original)) == material_hash(
        material_payload("clinicaltrials", retrieved_again)
    )
    assert material_hash(material_payload("clinicaltrials", original)) != material_hash(
        material_payload("clinicaltrials", corrected)
    )


def test_regulatory_and_patent_hashes_ignore_ingestion_timestamps():
    regulatory = {
        "raw_payload": {"status": "approved", "application": "NDA123"},
        "metadata": {"retrieved_at": "2026-01-01T00:00:00Z"},
    }
    regulatory_again = {
        **regulatory,
        "metadata": {"retrieved_at": "2026-02-01T00:00:00Z"},
    }
    patent = {
        "title": "Patent",
        "raw_payload": {"status": "active"},
        "metadata": {"retrieved_at": "2026-01-01T00:00:00Z"},
    }
    patent_again = {
        **patent,
        "metadata": {"retrieved_at": "2026-02-01T00:00:00Z"},
    }
    assert material_hash(material_payload("regulatory", regulatory)) == material_hash(
        material_payload("regulatory", regulatory_again)
    )
    assert material_hash(material_payload("patent", patent)) == material_hash(
        material_payload("patent", patent_again)
    )


def test_changed_fields_are_stable_and_metadata_only_differences_are_excluded():
    before = {
        "title": "Old",
        "metadata": {"status": "PENDING", "retrieved_at": "before"},
    }
    after = {
        "title": "New",
        "metadata": {"status": "APPROVED", "retrieved_at": "after"},
    }
    old_material = material_payload("regulatory", before)
    new_material = material_payload("regulatory", after)
    assert changed_material_fields(old_material, new_material) == [
        "metadata.status",
        "title",
    ]
    old_retrieval = material_payload(
        "regulatory",
        {"title": "Same", "metadata": {"retrieved_at": "before"}},
    )
    new_retrieval = material_payload(
        "regulatory",
        {"title": "Same", "metadata": {"retrieved_at": "after"}},
    )
    assert changed_material_fields(old_retrieval, new_retrieval) == []

    changed = changed_material_fields(
        {"status": "PENDING"}, {"status": "APPROVED"}
    )
    assert changed == ["status"]


def test_event_identity_is_deterministic_per_transition_and_tenant_scoped():
    tenant_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    tenant_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    previous_snapshot = UUID("11111111-1111-1111-1111-111111111111")
    current_snapshot = UUID("22222222-2222-2222-2222-222222222222")
    args = ("pubmed", "PMID:123", previous_snapshot, current_snapshot)
    first = monitoring_event_id(*args, tenant_a)
    assert first == monitoring_event_id(*args, tenant_a)
    assert first != monitoring_event_id(*args, tenant_b)
    assert first != monitoring_event_id(
        "pubmed",
        "PMID:123",
        current_snapshot,
        previous_snapshot,
        tenant_a,
    )


@pytest.mark.asyncio
async def test_material_event_recalculates_decision_and_records_evidence(monkeypatch):
    organization_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    event_id = uuid4()
    snapshot_id = uuid4()
    manager = PostgresManager()

    class StubDecisionEngine:
        def evaluate(self, asset_id, tenant_id=None, policy=None, **kwargs):
            return SimpleNamespace(
                decision=SimpleNamespace(value="PURSUE"),
                score=81.0,
                confidence=0.91,
                recommended_action="PURSUE",
                supporting_evidence=["evidence://A"],
                negative_drivers=[],
                positive_drivers=["commercial"],
                upstream_signal_availability={"commercial": "AVAILABLE"},
            )

    class FakeConnection:
        def __init__(self):
            self.executed = []

        async def fetchrow(self, query, *args):
            if "FROM literature_decision_recalculations" in query and "monitoring_event_id" in query:
                return None
            if "FROM literature_source_snapshots" in query:
                return {
                    "id": snapshot_id,
                    "source": "company_events",
                    "source_id": "asset-123",
                    "tenant_id": organization_id,
                    "material_payload": {
                        "asset_id": "asset-123",
                        "event_type": "strategic_partnership",
                        "source_record": {"status": "active"},
                    },
                    "raw_payload": {"status": "active"},
                }
            if "FROM literature_decision_recalculations" in query and "current_decision_state" in query:
                return None
            return None

        async def execute(self, query, *args):
            self.executed.append((query, args))
            return None

    conn = FakeConnection()
    monkeypatch.setattr(manager, "_load_decision_engine", lambda: (StubDecisionEngine, lambda: None))
    await manager._process_event_recalculation(
        conn,
        {
            "id": event_id,
            "source": "company_events",
            "source_id": "asset-123",
            "tenant_id": organization_id,
            "current_snapshot_id": snapshot_id,
            "change_type": "material_change",
            "changed_fields": ["status"],
            "evidence_refs": [{"reference": "evidence://A", "kind": "company_event"}],
            "materiality_rationale": "Commercial status changed",
        },
    )

    assert any("INSERT INTO literature_decision_recalculations" in q for q, _ in conn.executed)
    assert any("UPDATE literature_monitoring_events" in q for q, _ in conn.executed)
    assert any("PURSUE" in json.dumps(args, default=str) for q, args in conn.executed)


@pytest.mark.asyncio
async def test_duplicate_material_event_does_not_create_duplicate_decision(monkeypatch):
    organization_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    event_id = uuid4()
    snapshot_id = uuid4()
    manager = PostgresManager()

    class FakeConnection:
        def __init__(self):
            self.executed = []

        async def fetchrow(self, query, *args):
            if "monitoring_event_id" in query:
                return {"id": uuid4(), "recalculation_status": "completed"}
            return None

        async def execute(self, query, *args):
            self.executed.append((query, args))
            return None

    conn = FakeConnection()
    monkeypatch.setattr(manager, "_load_decision_engine", lambda: (object, object))
    await manager._process_event_recalculation(
        conn,
        {
            "id": event_id,
            "source": "company_events",
            "source_id": "asset-123",
            "tenant_id": organization_id,
            "current_snapshot_id": snapshot_id,
            "change_type": "material_change",
            "changed_fields": ["status"],
            "evidence_refs": [{"reference": "evidence://same"}],
        },
    )
    assert conn.executed == []


@pytest.mark.asyncio
async def test_previous_decision_history_is_preserved_for_recalculation(monkeypatch):
    organization_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    event_id = uuid4()
    snapshot_id = uuid4()
    manager = PostgresManager()

    class StubDecisionEngine:
        def evaluate(self, asset_id, tenant_id=None, policy=None, **kwargs):
            return SimpleNamespace(
                decision=SimpleNamespace(value="MONITOR"),
                score=63.0,
                confidence=0.75,
                recommended_action="MONITOR",
                supporting_evidence=["evidence://B"],
                negative_drivers=["commercial"],
                positive_drivers=[],
                upstream_signal_availability={"commercial": "AVAILABLE"},
            )

    class FakeConnection:
        def __init__(self):
            self.executed = []

        async def fetchrow(self, query, *args):
            if "monitoring_event_id" in query:
                return None
            if "FROM literature_source_snapshots" in query:
                return {
                    "id": snapshot_id,
                    "source": "compan" if False else "company_events",
                    "source_id": "asset-123",
                    "tenant_id": organization_id,
                    "material_payload": {"asset_id": "asset-123", "event_type": "new_status"},
                    "raw_payload": {"event_type": "new_status"},
                }
            if "current_decision_state" in query:
                return {
                    "current_decision_version": {"decision": "PURSUE", "score": 81.0},
                    "current_decision_state": "PURSUE",
                }
            return None

        async def execute(self, query, *args):
            self.executed.append((query, args))
            return None

    conn = FakeConnection()
    monkeypatch.setattr(manager, "_load_decision_engine", lambda: (StubDecisionEngine, lambda: None))
    await manager._process_event_recalculation(
        conn,
        {
            "id": event_id,
            "source": "company_events",
            "source_id": "asset-123",
            "tenant_id": organization_id,
            "current_snapshot_id": snapshot_id,
            "change_type": "material_change",
            "changed_fields": ["status"],
            "evidence_refs": [{"reference": "evidence://B", "kind": "company_event"}],
            "materiality_rationale": "Commercial signal was updated",
        },
    )

    update_statement = next(args for q, args in conn.executed if "UPDATE literature_monitoring_events" in q)
    assert "PURSUE" in json.dumps(update_statement, default=str)


@pytest.mark.asyncio
async def test_failed_recalculation_is_retried_without_duplicate_decision(monkeypatch):
    organization_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    event_id = uuid4()
    snapshot_id = uuid4()
    calc_id = uuid4()
    manager = PostgresManager()

    class StubDecisionEngine:
        def __init__(self):
            self.calls = 0

        def evaluate(self, asset_id, tenant_id=None, policy=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient failure")
            return SimpleNamespace(
                decision=SimpleNamespace(value="PURSUE"),
                score=88.0,
                confidence=0.92,
                recommended_action="PURSUE",
                supporting_evidence=["evidence://retry"],
                negative_drivers=[],
                positive_drivers=["commercial"],
                upstream_signal_availability={"commercial": "AVAILABLE"},
            )

    engine = StubDecisionEngine()

    class FakeConnection:
        def __init__(self):
            self.executed = []
            self.fetch_sequence = [
                None,
                {
                    "id": snapshot_id,
                    "source": "company_events",
                    "source_id": "asset-123",
                    "tenant_id": organization_id,
                    "material_payload": {"asset_id": "asset-123", "event_type": "new_status"},
                    "raw_payload": {"event_type": "new_status"},
                },
                {"id": calc_id, "recalculation_status": "failed"},
                {
                    "id": snapshot_id,
                    "source": "company_events",
                    "source_id": "asset-123",
                    "tenant_id": organization_id,
                    "material_payload": {"asset_id": "asset-123", "event_type": "recovered_status"},
                    "raw_payload": {"event_type": "recovered_status"},
                },
                None,
            ]

        async def fetchrow(self, query, *args):
            if not self.fetch_sequence:
                return None
            return self.fetch_sequence.pop(0)

        async def execute(self, query, *args):
            self.executed.append((query, args))
            return None

    conn = FakeConnection()
    monkeypatch.setattr(manager, "_load_decision_engine", lambda: (lambda: engine, lambda: None))
    await manager._process_event_recalculation(
        conn,
        {
            "id": event_id,
            "source": "company_events",
            "source_id": "asset-123",
            "tenant_id": organization_id,
            "current_snapshot_id": snapshot_id,
            "change_type": "material_change",
            "changed_fields": ["status"],
            "evidence_refs": [{"reference": "evidence://retry", "kind": "company_event"}],
            "materiality_rationale": "Retry after transient failure",
        },
    )
    assert any("recalculation_status = 'failed'" in q for q, _ in conn.executed)
    assert material_hash({"a": 1, "b": {"x": 2}}) == material_hash(
        {"b": {"x": 2}, "a": 1}
    )


@pytest.mark.asyncio
async def test_event_listing_queries_only_the_trusted_tenant():
    organization_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    captured = {}

    class Connection:
        async def fetch(self, query, *args):
            captured["query"] = query
            captured["args"] = args
            return []

    @asynccontextmanager
    async def acquire(organization_id=None):
        captured["tenant_context"] = organization_id
        yield Connection()

    manager = PostgresManager()
    manager.acquire = acquire
    await manager.list_monitoring_events(
        organization_id=organization_id,
        source_category="publications",
        limit=25,
    )

    assert "tenant_id IS NOT DISTINCT FROM $1::uuid" in captured["query"]
    assert captured["tenant_context"] == str(organization_id)
    assert captured["args"] == (organization_id, "publications", 25)


def test_monitoring_api_uses_trusted_tenant_context(monkeypatch):
    organization_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    event_id = UUID("11111111-1111-1111-1111-111111111111")
    snapshot_id = UUID("22222222-2222-2222-2222-222222222222")
    detected_at = "2026-10-09T12:00:00Z"
    list_events = AsyncMock(
        return_value=[
            {
                "id": event_id,
                "source": "pubmed",
                "source_category": "publications",
                "source_id": "PMID:123",
                "change_type": "new_source_record",
                "previous_content_hash": None,
                "current_content_hash": "hash",
                "previous_material_hash": None,
                "current_material_hash": "material",
                "previous_snapshot_id": None,
                "current_snapshot_id": snapshot_id,
                "source_event_at": None,
                "detected_at": detected_at,
                "changed_fields": '["title"]',
                "evidence_refs": "[]",
                "materiality_rationale": "First observed version.",
                "canonical_entity_id": None,
                "canonical_resolution_status": "unresolved",
                "recalculation_status": "not_supported",
                "decision_change_state": "unavailable",
                "created_at": detected_at,
            }
        ]
    )
    monkeypatch.setattr(postgres_module.postgres_manager, "pool", object())
    monkeypatch.setattr(
        postgres_module.postgres_manager, "list_monitoring_events", list_events
    )
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        organization_id=str(organization_id)
    )
    try:
        response = TestClient(app).get(
            "/api/v1/monitoring/events?source_category=publications&tenant_id=attacker"
        )
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)

    assert response.status_code == 200
    assert response.json()["items"][0]["source_id"] == "PMID:123"
    assert list_events.await_args.kwargs == {
        "organization_id": organization_id,
        "limit": 50,
        "source_category": "publications",
    }
