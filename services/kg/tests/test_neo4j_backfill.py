from pathlib import Path
from uuid import UUID

import pytest

from app.core.canonical_security import CanonicalPrincipal
from app.core.neo4j_security import Neo4jScope
from app.services.backfill import CheckpointStore, neo4j_records, neo4j_relationships
from app.services.neo4j_backfill import apply_neo4j_record, run_neo4j_backfill


class Result:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for row in self.rows:
            yield row


class Session:
    def __init__(self, node_rows, relationship_rows):
        self.node_rows = node_rows
        self.relationship_rows = relationship_rows
        self.calls = 0

    async def run(self, query, **parameters):
        self.calls += 1
        if "MATCH (subject)-[r]->(object)" in query:
            return Result(self.relationship_rows)
        return Result(self.node_rows)


class Repository:
    def __init__(self):
        self.entities = {}
        self.identifiers = set()
        self.observations = set()
        self.relationships = set()

    async def reconcile_legacy_record(self, record, principal, **kwargs):
        source_id = record["source_record_id"]
        if source_id in self.entities:
            return {"status": "EXACT_MATCH", "canonical_entity_id": self.entities[source_id]}
        entity_id = UUID("11111111-1111-1111-1111-111111111111") if source_id == "legacy-1" else UUID("22222222-2222-2222-2222-222222222222")
        self.entities[source_id] = entity_id
        return {"status": "NEW_ENTITY", "canonical_entity_id": entity_id}

    async def ensure_identifier(self, entity_id, namespace, identifier_type, value, source_record, visibility, principal):
        self.identifiers.add((str(entity_id), namespace, identifier_type, value))

    async def ensure_observation(self, payload, principal):
        self.observations.add((str(payload.entity_id), payload.property_name))

    async def ensure_relationship(self, payload, principal):
        self.relationships.add((str(payload.subject_entity_id), payload.predicate, str(payload.object_entity_id)))

    async def get_reconciliation_for_source(self, source_type, source_record_id, tenant_id):
        entity_id = self.entities.get(source_record_id)
        return {"canonical_entity_id": entity_id} if entity_id else None


PRINCIPAL = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset({"graph:system"}))
SYSTEM_SCOPE = Neo4jScope(None, system=True)


def node(node_id="legacy-1", label="Target", **properties):
    return {
        "n": {"id": node_id, "name": properties.pop("name", "Legacy target"), **properties},
        "labels": [label],
    }


@pytest.mark.asyncio
async def test_neo4j_adapter_preserves_labels_identity_and_properties():
    records = [record async for record in neo4j_records(Session([node(source_id="SRC-1")], []), scope=SYSTEM_SCOPE)]
    assert records[0]["source_record_id"] == "legacy-1"
    assert records[0]["metadata"]["legacy_labels"] == ["Target"]
    assert records[0]["identifiers"][0]["value"] == "legacy-1"
    assert records[0]["metadata"]["legacy_properties"]["source_id"] == "SRC-1"


@pytest.mark.asyncio
async def test_cross_tenant_relationship_is_classified_and_not_migrated():
    rows = [{
        "subject_id": "a", "object_id": "b", "relationship_id": "rel-1",
        "relationship_type": "TARGETS", "relationship": {"predicate": "TARGETS"},
        "subject_tenant": "tenant-a", "object_tenant": "tenant-b",
    }]
    relationships = [relationship async for relationship in neo4j_relationships(Session([], rows), UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), SYSTEM_SCOPE)]
    assert relationships[0]["status"] == "CROSS_TENANT_REJECTED"


@pytest.mark.asyncio
async def test_apply_preserves_source_identifier_and_factual_observations():
    repository = Repository()
    record = (await _one_record())
    await apply_neo4j_record(repository, PRINCIPAL, record, {"canonical_entity_id": "11111111-1111-1111-1111-111111111111"})
    assert ("11111111-1111-1111-1111-111111111111", "neo4j", "neo4j_id", "legacy-1") in repository.identifiers
    assert ("11111111-1111-1111-1111-111111111111", "name") in repository.observations


async def _one_record():
    return [record async for record in neo4j_records(Session([node(created_at="2024-01-01T00:00:00")], []), scope=SYSTEM_SCOPE)][0]


@pytest.mark.asyncio
async def test_runner_is_idempotent_and_isolates_malformed_nodes(tmp_path: Path):
    repository = Repository()
    session = Session([node(), {"n": {"id": "bad"}, "labels": ["Unknown"]}, node("legacy-2", name="Legacy disease")], [])
    result = await run_neo4j_backfill(repository, PRINCIPAL, session, CheckpointStore(tmp_path / "checkpoint.json"), create_if_unresolved=True)
    assert result["counts"]["new_entity"] == 2
    assert result["counts"]["failed"] == 1
    assert result["failures"][0]["source_record_id"] == "bad"

    restarted = await run_neo4j_backfill(repository, PRINCIPAL, session, CheckpointStore(tmp_path / "checkpoint.json"), create_if_unresolved=True)
    assert restarted["counts"]["skipped"] == 2
    assert len(repository.identifiers) == 2
    assert len(repository.observations) == 4


@pytest.mark.asyncio
async def test_dry_run_does_not_persist_nodes_or_relationships():
    repository = Repository()
    relationship = {
        "subject_id": "legacy-1", "object_id": "legacy-2", "relationship_id": "rel-1",
        "relationship_type": "TARGETS", "relationship": {"predicate": "TARGETS"},
        "subject_tenant": None, "object_tenant": None,
    }
    result = await run_neo4j_backfill(
        repository,
        PRINCIPAL,
        Session([node(), node("legacy-2", name="Legacy target 2")], [relationship]),
        dry_run=True,
        create_if_unresolved=True,
    )
    assert result["counts"]["total"] == 2
    assert result["counts"]["relationship_total"] == 1
    assert not repository.identifiers
    assert not repository.observations
    assert not repository.relationships


@pytest.mark.asyncio
async def test_supported_relationship_migrates_once(tmp_path: Path):
    repository = Repository()
    relationship = {
        "subject_id": "legacy-1", "object_id": "legacy-2", "relationship_id": "rel-1",
        "relationship_type": "TARGETS", "relationship": {"predicate": "TARGETS"},
        "subject_tenant": None, "object_tenant": None,
    }
    session = Session([node(), node("legacy-2", name="Legacy target 2")], [relationship])
    first = await run_neo4j_backfill(repository, PRINCIPAL, session, CheckpointStore(tmp_path / "checkpoint.json"), create_if_unresolved=True)
    second = await run_neo4j_backfill(repository, PRINCIPAL, session, CheckpointStore(tmp_path / "checkpoint-2.json"), create_if_unresolved=True)
    assert first["counts"]["relationship_migrated"] == 1
    assert second["counts"]["relationship_migrated"] == 1
    assert len(repository.relationships) == 1
