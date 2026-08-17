"""Canonical knowledge representation shared by the KG client, the LLM Wiki
client, and the chunking pipeline.

This module intentionally does not introduce a new persistence layer or a
new entity taxonomy — it normalizes the literature pipeline's existing
NER/relationship output (see app/nlp/ner.py, app/nlp/relationship_extractor.py)
onto the entity labels and relationship types already defined by the
Knowledge Graph service (services/kg/app/schemas/{nodes,relationships}.py),
and defines the metadata/tenant shape that the LLM Wiki write path
(app/integrations/wiki_client.py) and the search hand-off
(app/services/search_integration.py) both need.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Fixed namespace so the same (category, text) pair always resolves to the
# same UUID across pipeline runs — this is what lets a wiki chunk's
# entity_ids be traced back to the matching Neo4j node id without a round
# trip to the KG service.
_ENTITY_ID_NAMESPACE = uuid.UUID("6f6d0f2e-6e0a-4f0b-9a6b-2e6b7f9c9e10")

# NER `type` (see app/nlp/ner.py) -> Knowledge Graph node label
# (see services/kg/app/schemas/nodes.py::VALID_LABELS). Both singular
# ("drug", the NER `type` field) and plural ("drugs", the NER `category`
# field) spellings are mapped, since callers may only have one or the
# other (see app/nlp/ner.py, which emits both on the same entity dict).
ENTITY_TYPE_TO_KG_LABEL: dict[str, str] = {
    "gene": "Gene",
    "genes": "Gene",
    "protein": "Protein",
    "proteins": "Protein",
    "disease": "Disease",
    "diseases": "Disease",
    "drug": "Drug",
    "drugs": "Drug",
    "target": "Target",
    "targets": "Target",
    "mutation": "Mutation",
    "mutations": "Mutation",
    "variant": "Mutation",
    "variants": "Mutation",
    "publication": "Publication",
    "publications": "Publication",
    "patent": "Patent",
    "patents": "Patent",
    "clinical_trial": "ClinicalTrial",
    "clinical_trials": "ClinicalTrial",
    "company": "Company",
    "companies": "Company",
    "organization": "Company",
    "organizations": "Company",
    "conference": "Conference",
    "conferences": "Conference",
    "biomarker": "Biomarker",
    "biomarkers": "Biomarker",
}

# Relationship `predicate` (see app/nlp/relationship_extractor.py) -> KG
# relationship type (see services/kg/app/schemas/relationships.py::
# VALID_RELATIONSHIP_TYPES). The KG's relationship vocabulary is generic,
# so predicates without an exact semantic match fall back to INTERACTS
# rather than being silently dropped.
RELATIONSHIP_PREDICATE_TO_KG_TYPE: dict[str, str] = {
    "treats": "TREATS",
    "targets": "TARGETS",
    "interacts_with": "INTERACTS",
    "associated_with": "INTERACTS",
    "presented_at": "PRESENTED_AT",
    "published_in": "PUBLISHED_IN",
    "owned_by": "OWNED_BY",
    "competes_with": "COMPETES_WITH",
    "validated_by": "VALIDATED_BY",
}


def deterministic_entity_id(category: str, text: str) -> str:
    """Stable UUID for an entity, derived from its normalized text + category.

    Using a deterministic id (rather than a random one per pipeline run)
    means the same concept always lands on the same KG node and the same
    wiki page across repeated ingestions, which is what makes wiki
    `entity_ids` traceable back to graph entities.
    """
    normalized = f"{category.strip().lower()}:{text.strip().lower()}"
    return str(uuid.uuid5(_ENTITY_ID_NAMESPACE, normalized))


def normalize_entity_label(entity_type: str) -> str | None:
    """Map a literature NER entity type to a valid KG node label, or None."""
    return ENTITY_TYPE_TO_KG_LABEL.get((entity_type or "").strip().lower())


def normalize_relationship_type(predicate: str) -> str | None:
    """Map a literature relationship predicate to a valid KG relationship type, or None."""
    return RELATIONSHIP_PREDICATE_TO_KG_TYPE.get((predicate or "").strip().lower())


@dataclass(frozen=True)
class TenantContext:
    """Organization/workspace/project/user scope for a request or pipeline run.

    Mirrors services/auth's tenant claim shape (organizationId/roles today,
    workspaceId/projectId anticipated — see services/auth/src/abac.ts's
    ResourceAttributes) so any isolation added here lines up with the
    isolation model already used by the auth service's Postgres RLS.
    """

    organization_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None

    def is_scoped(self) -> bool:
        return bool(self.organization_id)

    def as_dict(self) -> dict[str, str]:
        return {
            k: v
            for k, v in {
                "organization_id": self.organization_id,
                "workspace_id": self.workspace_id,
                "project_id": self.project_id,
                "user_id": self.user_id,
            }.items()
            if v
        }

    @classmethod
    def from_claims(cls, claims: dict[str, Any] | None) -> TenantContext:
        claims = claims or {}
        return cls(
            organization_id=claims.get("organization_id")
            or claims.get("organizationId"),
            workspace_id=claims.get("workspace_id") or claims.get("workspaceId"),
            project_id=claims.get("project_id") or claims.get("projectId"),
            user_id=claims.get("user_id") or claims.get("sub"),
        )


@dataclass
class KnowledgeMetadata:
    """Canonical metadata attached to every indexed document/chunk.

    Field names follow the Prompt 8 spec directly; source_type/source_id/
    provenance reuse the vocabulary already produced by
    app/connectors (pubmed/biorxiv/clinicaltrials/patent/conference/company)
    and app/services/evidence_ranking.py's provenance blocks.
    """

    document_id: str
    source_type: str
    source_id: str
    title: str
    entity_ids: list[str] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=list)
    organization_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    version: int = 1
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    provenance: dict[str, Any] = field(default_factory=dict)
    citation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "entity_ids": self.entity_ids,
            "entity_types": self.entity_types,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provenance": self.provenance,
            "citation": self.citation,
        }
