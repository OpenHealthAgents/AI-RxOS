from __future__ import annotations

import asyncio
from uuid import UUID

from app.core.config import get_settings
from app.core.canonical_security import CanonicalPrincipal
from app.database.canonical_store import canonical_store
from app.schemas.canonical import (
    AliasInput,
    CanonicalEntityCreate,
    CanonicalRelationshipCreate,
    EntityType,
    IdentifierInput,
    Modality,
    ObservationKind,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_repository import CanonicalRepository

DEMO_PROVENANCE = {
    "fixture": "ai-rxos-phase-2-demo-v1",
    "synthetic": True,
    "scientific_claims": False,
    "description": "Structural demo fixture only; not a source-backed scientific assertion.",
}

ENTITIES = [
    ("target", "ERBB2", "target", {"gene_symbol": "ERBB2", "target_class": "demo_fixture"}, ["HER2"]),
    ("target", "ESR1", "target", {"gene_symbol": "ESR1", "target_class": "demo_fixture"}, []),
    ("target", "CDK4/6", "target", {"target_class": "demo_fixture"}, []),
    ("target", "TACSTD2", "target", {"gene_symbol": "TACSTD2", "target_class": "demo_fixture"}, ["TROP2"]),
    ("target", "VTCN1", "target", {"gene_symbol": "VTCN1", "target_class": "demo_fixture"}, ["B7-H4"]),
    ("disease", "Breast cancer (demo fixture)", "disease", {"disease_context": "synthetic demonstration only"}, []),
    ("biomarker", "HER2 (demo biomarker)", "biomarker", {"biomarker_type": "protein", "disease_context": "synthetic demonstration only"}, []),
    ("company", "DEMO Biopharma (synthetic)", "company", {"company_type": "synthetic_fixture"}, []),
    ("asset", "DEMO-ADC-001 (synthetic)", "asset", {"development_names": ["DEMO-ADC-001"], "development_status": "synthetic_demo_only"}, []),
    ("trial", "DEMO-TRIAL-001 (not real)", "trial", {"title": "Synthetic fixture; not a clinical study", "status": "not_a_real_trial"}, []),
    ("publication", "DEMO-PUB-001 (not real)", "publication", {"article_type": "synthetic_fixture"}, []),
    ("patent", "DEMO-PATENT-001 (not real)", "patent", {"status": "not_a_real_patent"}, []),
    ("regulatory", "DEMO-REG-001 (not real)", "regulatory", {"decision": "not_a_real_regulatory_event"}, []),
    ("mechanism", "DEMO-MOA-001 (hypothetical)", "mechanism", {"mechanism_type": "hypothetical_fixture"}, []),
    ("combination", "DEMO-COMBO-001 (hypothetical)", "combination", {"study_context": "not an efficacy claim"}, []),
    ("resistance", "DEMO-RESISTANCE-001 (hypothetical)", "resistance", {"resistance_status": "hypothesis"}, []),
]

ENTITY_TYPES = {
    "target": EntityType.TARGET,
    "disease": EntityType.DISEASE,
    "biomarker": EntityType.BIOMARKER,
    "company": EntityType.COMPANY,
    "asset": EntityType.THERAPEUTIC_ASSET,
    "trial": EntityType.CLINICAL_TRIAL,
    "publication": EntityType.PUBLICATION,
    "patent": EntityType.PATENT,
    "regulatory": EntityType.REGULATORY_EVENT,
    "mechanism": EntityType.MECHANISM,
    "combination": EntityType.COMBINATION,
    "resistance": EntityType.RESISTANCE_MECHANISM,
}


async def main() -> None:
    settings = get_settings()
    await canonical_store.initialize(settings.database_url)
    repository = CanonicalRepository(canonical_store)
    operator = CanonicalPrincipal(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        organization_id=None,
        roles=frozenset({"operator", "reviewer"}),
        permissions=frozenset(),
    )
    ids = {}
    try:
        for key, name, id_type, attributes, aliases in ENTITIES:
            external_id = f"{key}:{name}"
            resolved = await repository.resolve_identifier("ai-rxos-demo", id_type, external_id, operator)
            if resolved["status"] == "resolved":
                ids[key] = str(resolved["entity"]["id"])
                continue
            entity_type = ENTITY_TYPES[key]
            modality = Modality.ADC if key == "asset" else None
            created = await repository.create_entity(
                CanonicalEntityCreate(
                    entity_type=entity_type,
                    preferred_name=name,
                    description="Synthetic demo fixture; not a source-backed scientific fact.",
                    modality=modality,
                    lifecycle_status="synthetic_demo_only" if key == "asset" else None,
                    visibility=Visibility.GLOBAL,
                    attributes=attributes,
                    source_record=SourceRecordInput(
                        namespace="ai-rxos-demo",
                        external_id=f"source:{external_id}",
                        source_type="demo",
                        provenance=DEMO_PROVENANCE,
                    ),
                    identifiers=[IdentifierInput(
                        namespace="ai-rxos-demo",
                        identifier_type=id_type,
                        value=external_id,
                        source_record=SourceRecordInput(
                            namespace="ai-rxos-demo",
                            external_id=f"identifier:{external_id}",
                            source_type="demo",
                            provenance=DEMO_PROVENANCE,
                        ),
                    )],
                    aliases=[AliasInput(
                        value=alias,
                        alias_type="synonym",
                        source_record=SourceRecordInput(
                            namespace="ai-rxos-demo",
                            external_id=f"alias:{external_id}:{alias}",
                            source_type="demo",
                            provenance=DEMO_PROVENANCE,
                        ),
                    ) for alias in aliases],
                ),
                operator,
            )
            ids[key] = str(created["id"])

        for relationship_key, subject_key, predicate, object_key in (
            ("asset-target", "asset", "TARGETS", "target"),
            ("asset-disease", "asset", "INDICATED_FOR", "disease"),
            ("asset-company", "asset", "OWNED_BY", "company"),
            ("trial-asset", "trial", "STUDIES", "asset"),
            ("publication-asset", "publication", "MENTIONS", "asset"),
            ("patent-asset", "patent", "CLAIMS", "asset"),
            ("regulatory-asset", "regulatory", "CONCERNS", "asset"),
            ("mechanism-target", "mechanism", "INVOLVES", "target"),
            ("combination-asset", "combination", "CONTAINS", "asset"),
            ("resistance-asset", "resistance", "OBSERVED_FOR", "asset"),
        ):
            existing = await canonical_store.pool.fetchval(
                """SELECT r.id FROM canonical.relationships r
                JOIN canonical.source_records s ON s.id = (
                    SELECT o.source_record_id FROM canonical.observations o WHERE o.relationship_id = r.id LIMIT 1
                )
                WHERE r.predicate = $1 AND r.subject_entity_id = $2 AND r.object_entity_id = $3
                  AND s.namespace = 'ai-rxos-demo' AND s.external_id = $4""",
                predicate, UUID(ids[subject_key]), UUID(ids[object_key]), f"source:relationship:{relationship_key}",
            )
            if existing:
                continue
            await repository.create_relationship(
                CanonicalRelationshipCreate(
                    subject_entity_id=UUID(ids[subject_key]),
                    predicate=predicate,
                    object_entity_id=UUID(ids[object_key]),
                    source_record=SourceRecordInput(
                        namespace="ai-rxos-demo",
                        external_id=f"source:relationship:{relationship_key}",
                        source_type="demo",
                        provenance=DEMO_PROVENANCE,
                    ),
                    property_name="demo_relationship_fixture",
                    observation_value={"synthetic": True, "scientific_claim": False},
                    observation_kind=ObservationKind.HYPOTHESIS,
                ),
                operator,
            )
    finally:
        await canonical_store.close()


if __name__ == "__main__":
    asyncio.run(main())
