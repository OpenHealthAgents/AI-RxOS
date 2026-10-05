"""Replay source-owned records through the canonical reconciliation boundary.

This module deliberately contains orchestration only. Identity decisions remain
owned by ``CanonicalRepository.reconcile_legacy_record`` (B01).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, AsyncIterable, Awaitable, Callable
from uuid import UUID

from app.core.canonical_security import CanonicalPrincipal
from app.schemas.canonical import (
    CanonicalRelationshipCreate,
    EntityType,
    ObservationCreate,
    ObservationKind,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_repository import CanonicalRepository
from app.core.neo4j_security import Neo4jScope, require_scope


@dataclass
class BackfillCounts:
    total: int = 0
    exact_match: int = 0
    possible_match: int = 0
    ambiguous: int = 0
    unresolved: int = 0
    new_entity: int = 0
    failed: int = 0
    skipped: int = 0

    def add(self, status: str) -> None:
        key = status.lower()
        if hasattr(self, key):
            setattr(self, key, getattr(self, key) + 1)

    def as_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass
class BackfillResult:
    counts: BackfillCounts = field(default_factory=BackfillCounts)
    failures: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"counts": self.counts.as_dict(), "failures": self.failures}


class CheckpointStore:
    """Small durable checkpoint store for restart-safe source replay."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.completed: set[str] = set()
        if self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.completed = {str(item) for item in payload.get("completed", [])}

    def contains(self, key: str) -> bool:
        return key in self.completed

    def add(self, key: str) -> None:
        self.completed.add(key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"completed": sorted(self.completed)}), encoding="utf-8")


def _record_key(record: dict[str, Any]) -> str:
    source = str(record.get("source_type") or "legacy")
    source_id = str(record.get("source_record_id") or record.get("source_id") or "")
    tenant = str(record.get("tenant_id") or "global")
    return hashlib.sha256(f"{source}\0{source_id}\0{tenant}".encode()).hexdigest()


def _json_field(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value if value is not None else fallback


class CanonicalBackfill:
    def __init__(
        self,
        repository: CanonicalRepository,
        principal: CanonicalPrincipal,
        checkpoint: CheckpointStore | None = None,
    ) -> None:
        self.repository = repository
        self.principal = principal
        self.checkpoint = checkpoint

    async def run(
        self,
        records: AsyncIterable[dict[str, Any]],
        *,
        dry_run: bool = False,
        create_if_unresolved: bool = False,
        apply_record: Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]] | None = None,
    ) -> BackfillResult:
        result = BackfillResult()
        async for record in records:
            result.counts.total += 1
            key = _record_key(record)
            if self.checkpoint and self.checkpoint.contains(key):
                result.counts.skipped += 1
                continue
            try:
                normalized = normalize_legacy_record(record)
                reconciliation = await self.repository.reconcile_legacy_record(
                    normalized,
                    self.principal,
                    create_if_unresolved=create_if_unresolved,
                    dry_run=dry_run,
                )
                result.counts.add(reconciliation["status"])
                if apply_record and not dry_run and reconciliation.get("canonical_entity_id"):
                    await apply_record(normalized, reconciliation)
                if self.checkpoint and not dry_run:
                    self.checkpoint.add(key)
            except Exception as exc:
                result.counts.failed += 1
                result.failures.append({"source_record_id": str(record.get("source_record_id", "")), "error": str(exc)})
        return result


def normalize_legacy_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate the source boundary while preserving source-owned metadata."""
    source = SourceRecordInput.model_validate(record["source_record"])
    entity_type = str(record.get("entity_type") or "publication")
    if entity_type not in {item.value for item in EntityType}:
        raise ValueError(f"unsupported canonical entity type: {entity_type}")
    names = [str(value).strip() for value in record.get("names", []) if str(value).strip()]
    if not names:
        raise ValueError("legacy record must contain at least one name")
    normalized = dict(record)
    normalized["source_record"] = source.model_dump(mode="json")
    normalized["entity_type"] = entity_type
    normalized["names"] = names
    normalized["identifiers"] = [dict(item) for item in record.get("identifiers", [])]
    return normalized


async def literature_records(rows: Any) -> AsyncIterable[dict[str, Any]]:
    """Adapt rows from the existing literature store without fabricating fields."""
    for row in rows:
        data = json.loads(json.dumps(dict(row), default=str))
        data["authors"] = _json_field(data.get("authors"), [])
        data["source_metadata"] = _json_field(data.get("source_metadata"), {})
        data["extracted_entities"] = _json_field(data.get("extracted_entities"), [])
        data["extracted_relationships"] = _json_field(data.get("extracted_relationships"), [])
        external_id = data.get("id") or data.get("pmid") or data.get("doi")
        if not external_id:
            raise ValueError("literature record has no durable source identifier")
        identifiers = [{
            "namespace": "literature",
            "identifier_type": "source_id",
            "value": str(external_id),
        }]
        for identifier_type in ("pmid", "pmcid", "doi"):
            value = data.get(identifier_type)
            if value:
                identifiers.append({
                    "namespace": "literature",
                    "identifier_type": identifier_type,
                    "value": str(value),
                })
        yield {
            "source_type": "literature",
            "source_record_id": str(external_id),
            "entity_type": "publication",
            "names": [data["title"]],
            "identifiers": identifiers,
            "tenant_id": data.get("tenant_id"),
            "relationships": data.get("extracted_relationships") or [],
            "extracted_entities": data.get("extracted_entities") or [],
            "metadata": {key: value for key, value in data.items() if key not in {"title", "id"}},
            "source_record": {
                "namespace": "literature",
                "external_id": str(external_id),
                "source_type": "publication",
                "published_at": data.get("published_at"),
                "provenance": {
                    "legacy_source": "literature",
                    "source_record_id": str(external_id),
                    "source_metadata": data,
                },
            },
        }


async def fetch_literature_rows(connection: Any, organization_id: UUID | None = None) -> AsyncIterable[dict[str, Any]]:
    """Read the existing durable literature table; absent columns remain absent."""
    query = """SELECT id, title, source, doi, published_at, citation_count, created_at,
            abstract, authors, pmid, pmcid, journal, source_metadata,
            extracted_entities, extracted_relationships, tenant_id
        FROM literature_papers
          WHERE (tenant_id IS NULL OR tenant_id = $1::uuid)
              OR public.literature_system_scope()
        ORDER BY id"""
    rows = await connection.fetch(query, organization_id)
    async for record in literature_records(rows):
        yield record


async def apply_literature_record(
    repository: CanonicalRepository,
    principal: Any,
    record: dict[str, Any],
    reconciliation: dict[str, Any],
) -> None:
    """Persist only source facts exposed by the historical literature schema."""
    entity_id = UUID(str(reconciliation["canonical_entity_id"]))
    organization_id = record.get("tenant_id")
    visibility = Visibility.TENANT if organization_id else Visibility.GLOBAL
    source_record = SourceRecordInput.model_validate(record["source_record"])

    for identifier in record.get("identifiers", []):
        await repository.ensure_identifier(
            entity_id,
            identifier["namespace"],
            identifier["identifier_type"],
            identifier["value"],
            source_record,
            visibility,
            principal,
        )

    metadata = record.get("metadata") or {}
    facts = {"title": record["names"][0]}
    for key in (
        "doi", "pmid", "pmcid", "abstract", "authors", "journal",
        "publication_date", "published_at", "citation_count", "source", "created_at",
    ):
        if metadata.get(key) is not None:
            facts[key] = metadata[key]
    if metadata.get("source_metadata"):
        facts["source_metadata"] = metadata["source_metadata"]
    for property_name, value in facts.items():
        await repository.ensure_observation(
            ObservationCreate(
                entity_id=entity_id,
                visibility=visibility,
                property_name=property_name,
                observation_kind=ObservationKind.SOURCE_FACT,
                value=value,
                source_record=source_record,
            ),
            principal,
        )

    for relationship in record.get("relationships") or []:
        subject_id = relationship.get("subject_entity_id")
        object_id = relationship.get("object_entity_id")
        predicate = relationship.get("predicate")
        if not subject_id or not object_id or not predicate:
            continue
        await repository.ensure_relationship(
            CanonicalRelationshipCreate(
                subject_entity_id=UUID(str(subject_id)),
                object_entity_id=UUID(str(object_id)),
                predicate=str(predicate),
                visibility=visibility,
                source_record=source_record,
                observation_value=relationship.get("value", relationship),
            ),
            principal,
        )


async def run_literature_backfill(
    repository: CanonicalRepository,
    principal: Any,
    literature_connection: Any,
    checkpoint: CheckpointStore | None = None,
    *,
    dry_run: bool = False,
    create_if_unresolved: bool = False,
) -> BackfillResult:
    backfill = CanonicalBackfill(repository, principal, checkpoint)
    callback = lambda record, reconciliation: apply_literature_record(
        repository, principal, record, reconciliation
    )
    return await backfill.run(
        fetch_literature_rows(literature_connection, principal.organization_id),
        dry_run=dry_run,
        create_if_unresolved=create_if_unresolved,
        apply_record=callback,
    )


async def neo4j_records(session: Any, organization_id: UUID | None = None, scope: Neo4jScope | None = None) -> AsyncIterable[dict[str, Any]]:
    """Adapt existing graph nodes; relationships are migrated separately only when supported."""
    scope = require_scope(scope)
    result = await session.run(
        """MATCH (n)
                WHERE n.id IS NOT NULL
                    AND NOT n:CanonicalEntity
                    AND NOT n:GraphVersion
                    AND ($system_scope OR (coalesce(n.visibility, 'global') = 'global'
                             OR ($organization_id IS NOT NULL AND
                                     coalesce(n.organization_id, n.tenant_id) = $organization_id))
                RETURN n, labels(n) AS labels""",
                organization_id=str(organization_id) if organization_id else None,
                system_scope=scope.system if scope else False,
    )
    async for row in result:
        node = dict(row["n"])
        labels = [str(label) for label in row["labels"]]
        source_id = str(node.get("id") or "")
        if not node.get("name"):
            yield _malformed_neo4j_record(source_id, labels, "missing name")
            continue
        visibility = str(node.get("visibility") or ("tenant" if node.get("organization_id") or node.get("tenant_id") else "global"))
        tenant_id = node.get("organization_id") or node.get("tenant_id")
        if visibility == "tenant" and not tenant_id:
            yield _malformed_neo4j_record(source_id, labels, "tenant-private node has no tenant identity")
            continue
        identifier = node.get("source_id") or node.get("external_id")
        identifiers = [{
            "namespace": "neo4j",
            "identifier_type": "neo4j_id",
            "value": source_id,
        }]
        if identifier:
            identifiers.append({
                "namespace": "neo4j",
                "identifier_type": "source_id",
                "value": str(identifier),
            })
        try:
            entity_type = str(node.get("entity_type") or _entity_type_from_labels(labels))
        except ValueError as exc:
            yield _malformed_neo4j_record(source_id, labels, str(exc), node.get("name"))
            continue
        aliases = _json_field(node.get("aliases"), [])
        yield {
            "source_type": "neo4j",
            "source_record_id": source_id,
            "entity_type": entity_type,
            "names": [str(node["name"])],
            "aliases": aliases if isinstance(aliases, list) else [],
            "identifiers": identifiers,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "metadata": {
                "legacy_neo4j_id": source_id,
                "legacy_labels": labels,
                "legacy_properties": node,
            },
            "attributes": _json_field(node.get("attributes_json") or node.get("attributes"), {}),
            "source_record": {
                "namespace": "neo4j",
                "external_id": source_id,
                "source_type": "database",
                "provenance": {"legacy_source": "neo4j", "legacy_labels": labels},
            },
        }


def _entity_type_from_labels(labels: list[str]) -> str:
    aliases = {
        "Drug": "therapeutic_asset",
        "Target": "target",
        "Disease": "disease",
        "Publication": "publication",
        "ClinicalTrial": "clinical_trial",
        "Company": "company",
        "Biomarker": "biomarker",
        "CanonicalEntity": "target",
    }
    for label in labels:
        if label in aliases:
            return aliases[label]
    raise ValueError(f"legacy Neo4j labels do not map to a canonical entity type: {labels}")


async def neo4j_relationships(session: Any, organization_id: UUID | None = None, scope: Neo4jScope | None = None) -> AsyncIterable[dict[str, Any]]:
    scope = require_scope(scope)
    result = await session.run(
        """MATCH (subject)-[r]->(object)
        WHERE subject.id IS NOT NULL AND object.id IS NOT NULL
                    AND NOT subject:CanonicalEntity AND NOT object:CanonicalEntity
                    AND type(r) <> 'CANONICAL_RELATIONSHIP'
          AND ($system_scope OR (coalesce(subject.visibility, 'global') = 'global'
               OR ($organization_id IS NOT NULL AND
                   coalesce(subject.organization_id, subject.tenant_id) = $organization_id))
          AND ($system_scope OR (coalesce(object.visibility, 'global') = 'global'
               OR ($organization_id IS NOT NULL AND
                   coalesce(object.organization_id, object.tenant_id) = $organization_id))
        RETURN subject.id AS subject_id, object.id AS object_id,
            r.id AS relationship_id, type(r) AS relationship_type, r AS relationship,
            coalesce(subject.organization_id, subject.tenant_id) AS subject_tenant,
            coalesce(object.organization_id, object.tenant_id) AS object_tenant""",
        organization_id=str(organization_id) if organization_id else None,
        system_scope=scope.system if scope else False,
    )
    async for row in result:
        relationship = dict(row["relationship"])
        subject_tenant = row["subject_tenant"]
        object_tenant = row["object_tenant"]
        if subject_tenant and object_tenant and str(subject_tenant) != str(object_tenant):
            yield {
                "relationship_id": str(row["relationship_id"] or ""),
                "subject_id": str(row["subject_id"]),
                "object_id": str(row["object_id"]),
                "relationship_type": str(row["relationship_type"]),
                "status": "CROSS_TENANT_REJECTED",
                "metadata": relationship,
            }
            continue
        yield {
            "relationship_id": str(row["relationship_id"] or ""),
            "subject_id": str(row["subject_id"]),
            "object_id": str(row["object_id"]),
            "relationship_type": str(row["relationship_type"]),
            "status": "READY",
            "metadata": relationship,
            "tenant_id": str(subject_tenant or object_tenant) if subject_tenant or object_tenant else None,
        }


def _malformed_neo4j_record(
    source_id: str,
    labels: list[str],
    error: str,
    name: str | None = None,
) -> dict[str, Any]:
    return {
        "source_type": "neo4j",
        "source_record_id": source_id,
        "entity_type": "unknown",
        "names": [name] if name else [],
        "metadata": {"legacy_labels": labels, "adapter_error": error},
        "source_record": {
            "namespace": "neo4j",
            "external_id": source_id or "unknown",
            "source_type": "database",
            "provenance": {"legacy_source": "neo4j", "legacy_labels": labels, "adapter_error": error},
        },
    }