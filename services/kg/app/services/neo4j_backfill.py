from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.core.canonical_security import CanonicalPrincipal
from app.schemas.canonical import (
    CanonicalRelationshipCreate,
    ObservationCreate,
    ObservationKind,
    SourceType,
    SourceRecordInput,
    Visibility,
)
from app.services.backfill import (
    BackfillResult,
    CanonicalBackfill,
    CheckpointStore,
    neo4j_records,
    neo4j_relationships,
)
from app.services.canonical_repository import CanonicalRepository
from app.core.neo4j_security import system_scope, tenant_scope


def _source_record(record: dict[str, Any]) -> SourceRecordInput:
    return SourceRecordInput.model_validate(record["source_record"])


async def apply_neo4j_record(
    repository: CanonicalRepository,
    principal: CanonicalPrincipal,
    record: dict[str, Any],
    reconciliation: dict[str, Any],
) -> None:
    entity_id = UUID(str(reconciliation["canonical_entity_id"]))
    tenant_id = record.get("tenant_id")
    visibility = Visibility.TENANT if tenant_id or principal.organization_id else Visibility.GLOBAL
    source_record = _source_record(record)

    for identifier in record.get("identifiers") or []:
        await repository.ensure_identifier(
            entity_id,
            identifier["namespace"],
            identifier["identifier_type"],
            identifier["value"],
            source_record,
            visibility,
            principal,
        )

    properties = record.get("metadata", {}).get("legacy_properties", {})
    facts = {"name": record["names"][0]}
    for property_name in ("description", "source", "created_at", "updated_at"):
        if properties.get(property_name) is not None:
            facts[property_name] = properties[property_name]
    if record.get("metadata"):
        facts["source_metadata"] = record["metadata"]

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


async def _reconciliation_for_source(
    repository: CanonicalRepository,
    principal: CanonicalPrincipal,
    source_id: str,
) -> dict[str, Any] | None:
    return await repository.get_reconciliation_for_source("neo4j", source_id, principal.organization_id)


async def run_neo4j_backfill(
    repository: CanonicalRepository,
    principal: CanonicalPrincipal,
    session: Any,
    checkpoint: CheckpointStore | None = None,
    *,
    dry_run: bool = False,
    create_if_unresolved: bool = False,
) -> dict[str, Any]:
    mapping: dict[str, UUID] = {}
    failures: list[dict[str, str]] = []

    async def apply_node(record: dict[str, Any], reconciliation: dict[str, Any]) -> None:
        canonical_id = reconciliation.get("canonical_entity_id")
        if canonical_id:
            mapping[record["source_record_id"]] = UUID(str(canonical_id))
            await apply_neo4j_record(repository, principal, record, reconciliation)

    graph_scope = tenant_scope(principal) if principal.organization_id else system_scope(principal)
    nodes: BackfillResult = await CanonicalBackfill(
        repository, principal, checkpoint
    ).run(
        neo4j_records(session, principal.organization_id, graph_scope),
        dry_run=dry_run,
        create_if_unresolved=create_if_unresolved,
        apply_record=apply_node,
    )

    relationship_total = relationship_migrated = relationship_skipped = relationship_failed = 0
    async for relationship in neo4j_relationships(session, principal.organization_id, graph_scope):
        relationship_total += 1
        if dry_run:
            if relationship["status"] != "READY":
                relationship_skipped += 1
            continue
        if relationship["status"] != "READY":
            relationship_skipped += 1
            failures.append({
                "source_record_id": relationship["relationship_id"],
                "error": relationship["status"],
            })
            continue

        subject_id = mapping.get(relationship["subject_id"])
        object_id = mapping.get(relationship["object_id"])
        if subject_id is None:
            subject_result = await _reconciliation_for_source(repository, principal, relationship["subject_id"])
            subject_id = UUID(str(subject_result["canonical_entity_id"])) if subject_result and subject_result.get("canonical_entity_id") else None
        if object_id is None:
            object_result = await _reconciliation_for_source(repository, principal, relationship["object_id"])
            object_id = UUID(str(object_result["canonical_entity_id"])) if object_result and object_result.get("canonical_entity_id") else None
        predicate = str(relationship["metadata"].get("predicate") or relationship["relationship_type"]).upper()
        if subject_id is None or object_id is None:
            relationship_skipped += 1
            failures.append({"source_record_id": relationship["relationship_id"], "error": "endpoint unresolved or ambiguous"})
            continue
        if not predicate or not predicate[0].isalpha() or not predicate.replace("_", "").isalnum():
            relationship_failed += 1
            failures.append({"source_record_id": relationship["relationship_id"], "error": "unsupported relationship type"})
            continue
        tenant_id = relationship.get("tenant_id")
        source_record = SourceRecordInput(
            namespace="neo4j",
            external_id=relationship["relationship_id"],
            source_type=SourceType.DATABASE,
            provenance={"legacy_source": "neo4j", "legacy_relationship": relationship["metadata"]},
        )
        try:
            await repository.ensure_relationship(
                CanonicalRelationshipCreate(
                    subject_entity_id=subject_id,
                    object_entity_id=object_id,
                    predicate=predicate,
                    visibility=Visibility.TENANT if tenant_id else Visibility.GLOBAL,
                    source_record=source_record,
                    observation_value=relationship["metadata"],
                ),
                principal,
            )
            relationship_migrated += 1
        except Exception as exc:
            relationship_failed += 1
            failures.append({"source_record_id": relationship["relationship_id"], "error": str(exc)})

    return {
        "counts": {
            **nodes.counts.as_dict(),
            "relationship_total": relationship_total,
            "relationship_migrated": relationship_migrated,
            "relationship_skipped": relationship_skipped,
            "relationship_failed": relationship_failed,
        },
        "failures": nodes.failures + failures,
    }
