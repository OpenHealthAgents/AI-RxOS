from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.domain.canonical_model import StrategicAction
from app.opportunity_engine.evidence.models import (
    EvidenceSource,
    EvidenceExtraction,
    EvidenceObservation,
    DerivedFeature,
    ModelOutput,
    RecommendationLineage,
)


class ProvenanceStage(StrEnum):
    SOURCE = "source"
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    FEATURE_DERIVATION = "feature_derivation"
    MODEL_INPUT = "model_input"
    MODEL_OUTPUT = "model_output"
    DECISION_INPUT = "decision_input"


class ProvenanceNodeType(StrEnum):
    SOURCE = "source"
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    FEATURE_DERIVATION = "feature_derivation"
    MODEL_INPUT = "model_input"
    MODEL_OUTPUT = "model_output"
    DECISION_INPUT = "decision_input"
    RECOMMENDATION = "recommendation"


class ProvenanceEdgeType(StrEnum):
    EXTRACTED_FROM = "extracted_from"
    NORMALIZED_FROM = "normalized_from"
    DERIVED_FROM = "derived_from"
    FED_INTO_MODEL = "fed_into_model"
    PREDICTED_BY = "predicted_by"
    DECIDED_FROM = "decided_from"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


def compute_sha256(data: Any) -> str:
    """Computes deterministic SHA-256 hash of arbitrary dictionary or string data."""
    if isinstance(data, (dict, list)):
        payload_bytes = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    elif isinstance(data, str):
        payload_bytes = data.encode("utf-8")
    elif isinstance(data, bytes):
        payload_bytes = data
    else:
        payload_bytes = str(data).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()


class NormalizationRecord(BaseModel):
    """
    Provenance of observation normalization: maps raw text/value to standardized
    numeric value and unit via an explicit transformation rule.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    extraction_id: UUID
    asset_id: UUID
    raw_value: str
    normalized_value: float
    normalized_unit: str
    parameter_name: str
    normalizer_version: str = "v1.0"
    transformation_rule: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.95)
    content_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = compute_sha256({
                "id": str(self.id),
                "extraction_id": str(self.extraction_id),
                "asset_id": str(self.asset_id),
                "raw_value": self.raw_value,
                "normalized_value": self.normalized_value,
                "normalized_unit": self.normalized_unit,
                "parameter_name": self.parameter_name,
                "normalizer_version": self.normalizer_version,
                "transformation_rule": self.transformation_rule,
            })


class ModelInputRecord(BaseModel):
    """
    Provenance of model inputs: captures the exact feature vector fed into a model.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    model_name: str
    model_version: str = "v0.1"
    asset_id: UUID
    feature_ids: List[UUID]
    feature_vector: Dict[str, float]
    input_schema_version: str = "v1.0"
    content_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = compute_sha256({
                "id": str(self.id),
                "model_name": self.model_name,
                "model_version": self.model_version,
                "asset_id": str(self.asset_id),
                "feature_ids": [str(fid) for fid in sorted(self.feature_ids, key=lambda x: str(x))],
                "feature_vector": self.feature_vector,
                "input_schema_version": self.input_schema_version,
            })


class DecisionInputRecord(BaseModel):
    """
    Provenance of decision inputs: captures the model outputs and decision criteria
    fed into the final strategic recommendation.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    recommendation_id: UUID
    asset_id: UUID
    action: StrategicAction
    model_output_ids: List[UUID]
    model_scores: Dict[str, float]
    decision_policy_version: str = "v1.0"
    thresholds_applied: Dict[str, float] = Field(default_factory=dict)
    content_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = compute_sha256({
                "id": str(self.id),
                "recommendation_id": str(self.recommendation_id),
                "asset_id": str(self.asset_id),
                "action": str(self.action),
                "model_output_ids": [str(mid) for mid in sorted(self.model_output_ids, key=lambda x: str(x))],
                "model_scores": self.model_scores,
                "decision_policy_version": self.decision_policy_version,
                "thresholds_applied": self.thresholds_applied,
            })


class ProvenanceNode(BaseModel):
    """
    Immutable node in the cryptographic provenance DAG.
    Maintains content_hash and cryptographic parent_hashes linking backward in time.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    stage: ProvenanceStage
    node_type: ProvenanceNodeType
    entity_id: UUID
    label: str
    description: str = ""
    payload_summary: Dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    parent_hashes: List[str] = Field(default_factory=list)
    parent_node_ids: List[UUID] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProvenanceEdge(BaseModel):
    """
    Directed link in the provenance DAG connecting cause/ancestor to effect/derivative.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_node_id: UUID
    target_node_id: UUID
    source_stage: ProvenanceStage
    target_stage: ProvenanceStage
    edge_type: ProvenanceEdgeType
    weight: float = Field(ge=0.0, le=1.0, default=1.0)
    hash_signature: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: Any) -> None:
        if not self.hash_signature:
            self.hash_signature = compute_sha256({
                "id": str(self.id),
                "source_node_id": str(self.source_node_id),
                "target_node_id": str(self.target_node_id),
                "source_stage": str(self.source_stage),
                "target_stage": str(self.target_stage),
                "edge_type": str(self.edge_type),
            })


class TracebackStep(BaseModel):
    """Single stage node summary during backward graph traceback."""
    model_config = ConfigDict(from_attributes=True)
    stage: ProvenanceStage
    node_id: UUID
    entity_id: UUID
    label: str
    content_hash: str
    summary: Dict[str, Any]
    parent_node_ids: List[UUID] = Field(default_factory=list)


class ProvenanceTracebackResult(BaseModel):
    """
    Traceback result verifying unbroken linkage from final recommendation
    back through all 7 stages to root evidence sources.
    """
    model_config = ConfigDict(from_attributes=True)
    recommendation_id: UUID
    asset_id: UUID
    action: StrategicAction
    merkle_root_hash: str
    unbroken_chain: bool = True
    chain_length: int = 7
    terminal_decision: TracebackStep
    model_output_step: TracebackStep
    model_input_step: TracebackStep
    feature_derivation_steps: List[TracebackStep] = Field(default_factory=list)
    normalization_steps: List[TracebackStep] = Field(default_factory=list)
    extraction_steps: List[TracebackStep] = Field(default_factory=list)
    underlying_sources: List[EvidenceSource] = Field(default_factory=list)
    audit_hash_verified: bool = True


class ProvenanceGraph(BaseModel):
    """
    Immutable Directed Acyclic Graph (DAG) capturing end-to-end evidence lineage.
    """
    model_config = ConfigDict(from_attributes=True)
    recommendation_id: UUID
    asset_id: UUID
    root_source_ids: List[UUID] = Field(default_factory=list)
    nodes: List[ProvenanceNode] = Field(default_factory=list)
    edges: List[ProvenanceEdge] = Field(default_factory=list)
    stage_counts: Dict[ProvenanceStage, int] = Field(default_factory=dict)
    root_to_leaf_paths: List[List[UUID]] = Field(default_factory=list)
    is_dag_valid: bool = True
    is_immutable_verified: bool = True
    merkle_root_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
