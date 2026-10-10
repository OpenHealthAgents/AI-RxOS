from pathlib import Path
from uuid import UUID

import pytest

from app.core.canonical_security import CanonicalPrincipal
from app.core.neo4j_security import Neo4jScope
from app.services.backfill import (
    CanonicalBackfill,
    CheckpointStore,
    apply_literature_record,
    fetch_literature_rows,
    literature_records,
    neo4j_records,
    normalize_legacy_record,
)


class FakeRepository:
    def __init__(self):
        self.calls = []

    async def reconcile_legacy_record(self, record, principal, **kwargs):
        self.calls.append((record, kwargs))
        return {"status": record.get("expected_status", "NEW_ENTITY"), "canonical_entity_id": "entity-1"}


class ApplyRepository:
    def __init__(self):
        self.identifiers = []
        self.observations = []

    async def ensure_identifier(self, *args):
        self.identifiers.append(args[1:4])

    async def ensure_observation(self, payload, principal):
        self.observations.append((payload.property_name, payload.value))
        return None


def _record(source_id: str, status: str = "NEW_ENTITY"):
    return {
        "source_type": "literature",
        "source_record_id": source_id,
        "entity_type": "publication",
        "names": ["A real title"],
        "expected_status": status,
        "source_record": {
            "namespace": "literature",
            "external_id": source_id,
            "source_type": "publication",
        },
    }


@pytest.mark.parametrize("status", ["EXACT_MATCH", "POSSIBLE_MATCH", "AMBIGUOUS", "UNRESOLVED", "NEW_ENTITY"])
@pytest.mark.asyncio
async def test_backfill_preserves_all_b01_statuses(status):
    repository = FakeRepository()
    backfill = CanonicalBackfill(repository, CanonicalPrincipal(None, None, frozenset(), frozenset()))
    result = await backfill.run(_records([_record(status, status)]), dry_run=True)
    assert result.counts.as_dict()[status.lower()] == 1


async def _records(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_backfill_dry_run_does_not_apply_or_checkpoint(tmp_path: Path):
    repository = FakeRepository()
    checkpoint = CheckpointStore(tmp_path / "checkpoint.json")
    backfill = CanonicalBackfill(repository, CanonicalPrincipal(None, None, frozenset(), frozenset()), checkpoint)

    result = await backfill.run(_records([_record("one", "EXACT_MATCH")]), dry_run=True, create_if_unresolved=True)

    assert result.counts.as_dict() == {
        "total": 1, "exact_match": 1, "possible_match": 0, "ambiguous": 0,
        "unresolved": 0, "new_entity": 0, "failed": 0, "skipped": 0,
    }
    assert not checkpoint.path.exists()
    assert repository.calls[0][1] == {"create_if_unresolved": True, "dry_run": True}


@pytest.mark.asyncio
async def test_backfill_isolates_failures_and_restarts(tmp_path: Path):
    repository = FakeRepository()
    checkpoint = CheckpointStore(tmp_path / "checkpoint.json")
    backfill = CanonicalBackfill(repository, CanonicalPrincipal(None, None, frozenset(), frozenset()), checkpoint)

    result = await backfill.run(_records([_record("one"), {"source_record": {}}, _record("two")]))
    assert result.counts.total == 3
    assert result.counts.new_entity == 2
    assert result.counts.failed == 1

    restarted = CanonicalBackfill(repository, CanonicalPrincipal(None, None, frozenset(), frozenset()), CheckpointStore(checkpoint.path))
    second = await restarted.run(_records([_record("one"), _record("two")]))
    assert second.counts.skipped == 2
    assert second.counts.new_entity == 0


def test_normalization_rejects_missing_names():
    with pytest.raises(ValueError, match="at least one name"):
        normalize_legacy_record({"source_record": {"namespace": "x", "external_id": "1", "source_type": "publication"}})


@pytest.mark.asyncio
async def test_literature_adapter_preserves_available_source_fields():
    rows = [{
        "id": "paper-1",
        "title": "Historical paper",
        "source": "pubmed",
        "doi": "10.1000/example",
        "published_at": None,
        "citation_count": 4,
        "created_at": None,
    }]
    records = [record async for record in literature_records(rows)]
    assert records[0]["source_record_id"] == "paper-1"
    assert {item["identifier_type"] for item in records[0]["identifiers"]} == {"source_id", "doi"}
    assert records[0]["metadata"]["citation_count"] == 4


@pytest.mark.asyncio
async def test_literature_source_query_carries_tenant_scope():
    class Connection:
        def __init__(self):
            self.parameters = None

        async def fetch(self, query, *parameters):
            self.parameters = parameters
            assert "tenant_id IS NULL OR tenant_id = $1::uuid" in query
            return []

    connection = Connection()
    rows = [record async for record in fetch_literature_rows(
        connection,
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )]
    assert rows == []
    assert connection.parameters == (UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),)


@pytest.mark.asyncio
async def test_apply_persists_identifiers_and_only_source_facts():
    repository = ApplyRepository()
    record = {
        "source_record": {
            "namespace": "literature",
            "external_id": "paper-1",
            "source_type": "publication",
            "provenance": {"source_record_id": "paper-1"},
        },
        "names": ["Historical paper"],
        "identifiers": [
            {"namespace": "literature", "identifier_type": "source_id", "value": "paper-1"},
            {"namespace": "literature", "identifier_type": "doi", "value": "10.1000/example"},
        ],
        "metadata": {"citation_count": 4, "source": "pubmed"},
    }
    await apply_literature_record(
        repository,
        CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset()),
        record,
        {"canonical_entity_id": "11111111-1111-1111-1111-111111111111"},
    )
    assert len(repository.identifiers) == 2
    assert {item[0] for item in repository.observations} == {"title", "citation_count", "source"}


class FakeNeo4jResult:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for row in self.rows:
            yield row


class FakeNeo4jSession:
    def __init__(self, rows):
        self.rows = rows

    async def run(self, query, **parameters):
        return FakeNeo4jResult(self.rows)


@pytest.mark.asyncio
async def test_neo4j_adapter_preserves_identity_and_fails_private_unknown_tenant():
    rows = [{"n": {"id": "n-1", "name": "Target", "source_id": "HGNC:1"}, "labels": ["Target"]}]
    records = [record async for record in neo4j_records(FakeNeo4jSession(rows), scope=Neo4jScope(None, system=True))]
    assert records[0]["source_record_id"] == "n-1"
    assert records[0]["metadata"]["legacy_labels"] == ["Target"]
    assert records[0]["identifiers"][0]["value"] == "n-1"
    assert records[0]["identifiers"][1]["value"] == "HGNC:1"

    private_rows = [{"n": {"id": "n-2", "name": "Private", "visibility": "tenant"}, "labels": ["Target"]}]
    private_records = [record async for record in neo4j_records(FakeNeo4jSession(private_rows), scope=Neo4jScope(None, system=True))]
    assert private_records[0]["source_record_id"] == "n-2"
    assert "tenant identity" in private_records[0]["metadata"]["adapter_error"]