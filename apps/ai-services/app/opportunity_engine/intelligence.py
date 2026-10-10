"""Shared provenance-aware contracts for deterministic intelligence synthesis."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EpistemicClass(StrEnum):
    FACT = "FACT"
    DERIVED_FEATURE = "DERIVED_FEATURE"
    ML_PREDICTION = "ML_PREDICTION"
    AI_INFERENCE = "AI_INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


class IntelligenceValueStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class IntelligenceEvidence(BaseModel):
    """Source reference carried with an intelligence output."""

    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    source_type: str
    source_reference: str
    citation: str | None = None
    observed_at: date | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    epistemic_class: EpistemicClass = EpistemicClass.FACT
    provenance: dict[str, Any] = Field(default_factory=dict)


class IntelligenceValue(BaseModel):
    """Metric that explicitly distinguishes observed, derived, predicted, and unknown states."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    value: Any = None
    status: IntelligenceValueStatus = IntelligenceValueStatus.UNKNOWN
    epistemic_class: EpistemicClass = EpistemicClass.UNKNOWN
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    supporting_evidence: list[IntelligenceEvidence] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class IntelligenceRuleFinding(BaseModel):
    """Transparent deterministic rule result with explicit supporting evidence."""

    rule_id: str
    result: str
    applied: bool
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class IntelligenceModelComponent(BaseModel):
    """ML output envelope; absence of a model remains an explicit unavailable state."""

    model_name: str
    available: bool = False
    model_version: str | None = None
    feature_version: str | None = None
    prediction_cutoff: date
    predicted_value: float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    prediction_timestamp: datetime | None = None
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence_references: list[str] = Field(default_factory=list)
    reason: str | None = "No tenant-visible registered model is available."
    epistemic_class: EpistemicClass = EpistemicClass.UNKNOWN


class IntelligenceProfileBase(BaseModel):
    """Shared lineage fields for the three domain intelligence engines."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str
    tenant_id: str | None = None
    prediction_cutoff: date
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence: list[IntelligenceEvidence] = Field(default_factory=list)
    excluded_undated_evidence: list[IntelligenceEvidence] = Field(default_factory=list)
    knowledge_graph_evidence: list[IntelligenceEvidence] = Field(default_factory=list)
    rule_findings: list[IntelligenceRuleFinding] = Field(default_factory=list)
    ml_component: IntelligenceModelComponent
    epistemic_classes: list[EpistemicClass] = Field(
        default_factory=lambda: list(EpistemicClass)
    )


def unknown_value(
    name: str,
    reason: str,
    *,
    status: IntelligenceValueStatus = IntelligenceValueStatus.UNKNOWN,
    provenance: dict[str, Any] | None = None,
) -> IntelligenceValue:
    return IntelligenceValue(
        name=name,
        status=status,
        epistemic_class=EpistemicClass.UNKNOWN,
        confidence=None,
        reason=reason,
        provenance=provenance or {},
    )


def evidence_confidence(evidence: list[IntelligenceEvidence]) -> float | None:
    """Return the least source confidence; never invent a default or aggregate upward."""
    if not evidence or any(item.confidence is None for item in evidence):
        return None
    return min(item.confidence for item in evidence if item.confidence is not None)


def evidence_references(evidence: list[IntelligenceEvidence]) -> list[str]:
    return list(dict.fromkeys(item.source_reference for item in evidence))


def observed_intelligence_value(
    name: str,
    value: Any,
    evidence: list[IntelligenceEvidence],
    *,
    provenance: dict[str, Any] | None = None,
) -> IntelligenceValue:
    if not evidence:
        return unknown_value(name, "No cutoff-valid observed evidence supports this output.")
    return IntelligenceValue(
        name=name,
        value=value,
        status=IntelligenceValueStatus.AVAILABLE,
        epistemic_class=EpistemicClass.FACT,
        confidence=evidence_confidence(evidence),
        supporting_evidence=evidence,
        provenance=provenance or {},
    )


def registered_model_prediction(
    *,
    model_name: str,
    asset_id: str,
    prediction_cutoff: date,
    tenant_id: str | None,
    registry: Any | None,
    feature_store: Any | None,
    require_scientific_evidence: bool = False,
) -> tuple[IntelligenceModelComponent, Any | None]:
    """Serve only an exact tenant-visible artifact with a complete dated feature snapshot."""
    component = IntelligenceModelComponent(
        model_name=model_name,
        prediction_cutoff=prediction_cutoff,
    )
    if registry is None:
        component.reason = "No model registry was supplied."
        return component, None

    artifacts = [
        artifact
        for artifact in registry.list_models()
        if artifact.name == model_name
        and artifact.is_active
        and artifact.tenant_id in (None, tenant_id)
    ]
    if not artifacts:
        component.reason = f"No tenant-visible registered '{model_name}' model is available."
        return component, None
    if len(artifacts) != 1:
        component.reason = "A model version is required because multiple versions are registered."
        return component, None

    artifact = artifacts[0]
    component.model_version = artifact.version
    dataset_metadata = artifact.lineage.get("dataset_metadata", {})
    if not isinstance(dataset_metadata, dict):
        dataset_metadata = {}
    if require_scientific_evidence and (
        dataset_metadata.get("test_only") is True
        or dataset_metadata.get("test_fixture_scientific_evidence") is False
    ):
        component.reason = "Test-only or non-scientific training artifacts cannot serve intelligence."
        return component, None
    if artifact.training_cutoff is not None and artifact.training_cutoff > prediction_cutoff:
        component.reason = "Registered model training cutoff is later than this prediction cutoff."
        return component, None
    if artifact.tenant_id not in (None, tenant_id):
        component.reason = "Registered model is not visible to the requested tenant."
        return component, None
    if len(artifact.feature_versions) != 1:
        component.reason = "Model must have exactly one compatible feature version."
        return component, None
    component.feature_version = artifact.feature_versions[0]

    if feature_store is None:
        component.reason = "No feature store was supplied for point-in-time inference."
        return component, None
    feature_records = feature_store.get_feature_records_for_asset(
        asset_id,
        tenant_id=tenant_id,
    )
    selected: dict[str, Any] = {}
    for record in feature_records:
        if record.feature_version != component.feature_version:
            continue
        if record.feature_name not in artifact.feature_names:
            continue
        if record.observation_date > prediction_cutoff:
            continue
        if record.prediction_cutoff > prediction_cutoff:
            continue
        if record.value is None:
            continue
        if require_scientific_evidence:
            if (
                record.provenance.get("test_only") is True
                or record.provenance.get("scientific_evidence") is False
                or record.provenance.get("source_count") == 0
                or not record.evidence_references
                or any(
                    str(reference).lower().startswith("test-only:")
                    for reference in record.evidence_references
                )
            ):
                continue
        current = selected.get(record.feature_name)
        if current is None or (
            record.prediction_cutoff,
            record.observation_date,
            record.created_at,
        ) > (
            current.prediction_cutoff,
            current.observation_date,
            current.created_at,
        ):
            selected[record.feature_name] = record
    missing = set(artifact.feature_names) - set(selected)
    if missing:
        component.reason = (
            "Cutoff-valid tenant-scoped feature snapshot is incomplete: "
            + ", ".join(sorted(missing))
        )
        return component, None

    from app.ml.models import InferenceRequest
    from app.ml.serving import ModelServingEngine

    prediction = ModelServingEngine(
        registry=registry,
        feature_store=feature_store,
    ).predict(
        InferenceRequest(
            entity_id=asset_id,
            asset_id=asset_id,
            model_name=model_name,
            model_version=artifact.version,
            feature_version=component.feature_version,
            prediction_cutoff=prediction_cutoff,
            tenant_id=tenant_id,
        )
    )
    component.available = True
    component.predicted_value = prediction.probability
    component.confidence = prediction.confidence
    component.prediction_timestamp = prediction.prediction_timestamp
    component.input_snapshot = prediction.input_snapshot
    component.evidence_references = list(
        dict.fromkeys(
            reference
            for row in selected.values()
            for reference in row.evidence_references
        )
    )
    component.reason = None
    component.epistemic_class = EpistemicClass.ML_PREDICTION
    return component, prediction


def cutoff_valid_knowledge_graph_evidence(
    *,
    asset_id: str,
    prediction_cutoff: date,
    knowledge_graph: Any | None,
) -> list[IntelligenceEvidence]:
    """Return public KG relationships only when their evidence provenance predates cutoff."""
    if knowledge_graph is None:
        return []
    node = knowledge_graph.get_node_by_external_id(f"ASSET:{asset_id.upper()}")
    if node is None:
        return []
    graph = knowledge_graph.get_asset_opportunity_graph(node.id)
    evidence: list[IntelligenceEvidence] = []
    for relationships in graph.relationships_by_category.values():
        for relationship in relationships:
            for source in relationship.evidence_lineage:
                if source.created_at.date() > prediction_cutoff:
                    continue
                evidence.append(
                    IntelligenceEvidence(
                        evidence_id=str(source.evidence_id),
                        source_type=f"KNOWLEDGE_GRAPH:{relationship.relationship_category}",
                        source_reference=source.source_document_id or str(source.evidence_id),
                        citation=source.source_citation,
                        confidence=(
                            source.confidence
                            if "confidence" in source.model_fields_set
                            else None
                        ),
                        epistemic_class=EpistemicClass.FACT,
                        provenance={
                            "tenant_scope": "public_canonical_knowledge_graph",
                            "relationship_type": relationship.relationship_type.value,
                            "edge_id": str(relationship.edge_id),
                            "polarity": source.polarity,
                            "available_at": source.created_at.isoformat(),
                        },
                    )
                )
    return evidence
