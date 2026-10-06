from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 1. Knowledge Graph Node & Relationship Types
# ==============================================================================

class KGNodeType(str, Enum):
    ASSET = "ASSET"
    TARGET = "TARGET"
    GENE = "GENE"
    MUTATION = "MUTATION"
    PATHWAY = "PATHWAY"
    DISEASE = "DISEASE"
    INDICATION = "INDICATION"
    BIOMARKER = "BIOMARKER"
    PATIENT_POPULATION = "PATIENT_POPULATION"
    TRIAL = "TRIAL"
    PUBLICATION = "PUBLICATION"
    COMPANY = "COMPANY"
    INSTITUTION = "INSTITUTION"
    COMPETITOR = "COMPETITOR"
    RESISTANCE_MECHANISM = "RESISTANCE_MECHANISM"
    COMBINATION = "COMBINATION"
    PATENT = "PATENT"
    LICENSE = "LICENSE"
    REGULATORY_EVENT = "REGULATORY_EVENT"


class KGRelationshipType(str, Enum):
    TARGETS = "TARGETS"
    INVOLVES_GENE = "INVOLVES_GENE"
    HARBORS_MUTATION = "HARBORS_MUTATION"
    MODULATES_PATHWAY = "MODULATES_PATHWAY"
    TREATS_DISEASE = "TREATS_DISEASE"
    INDICATED_FOR = "INDICATED_FOR"
    STRATIFIED_BY_BIOMARKER = "STRATIFIED_BY_BIOMARKER"
    ENROLLS_POPULATION = "ENROLLS_POPULATION"
    EVALUATED_IN_TRIAL = "EVALUATED_IN_TRIAL"
    REPORTED_IN_PUB = "REPORTED_IN_PUB"
    DEVELOPED_BY_COMPANY = "DEVELOPED_BY_COMPANY"
    ORIGINATED_AT_INSTITUTION = "ORIGINATED_AT_INSTITUTION"
    COMPETES_WITH = "COMPETES_WITH"
    ACQUIRES_RESISTANCE = "ACQUIRES_RESISTANCE"
    OVERCOMES_RESISTANCE_VIA = "OVERCOMES_RESISTANCE_VIA"
    COVERED_BY_PATENT = "COVERED_BY_PATENT"
    SUBJECT_TO_LICENSE = "SUBJECT_TO_LICENSE"
    GOVERNED_BY_REGULATORY_EVENT = "GOVERNED_BY_REGULATORY_EVENT"


# ==============================================================================
# 2. Evidence Lineage
# ==============================================================================

class EdgeEvidenceProvenance(BaseModel):
    """
    Evidence lineage record linking a knowledge graph relationship
    back to its underlying literature, trial, regulatory, or patent source.
    """
    model_config = ConfigDict(from_attributes=True)
    evidence_id: UUID = Field(default_factory=uuid4)
    evidence_type: str = "LITERATURE"  # LITERATURE, CLINICAL_TRIAL, REGULATORY_RECORD, PATENT
    source_citation: str
    source_url: Optional[str] = None
    source_document_id: Optional[str] = None
    polarity: str = "SUPPORTING"  # SUPPORTING, CONTRADICTING, NEUTRAL
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 3. Nodes and Directed Edges
# ==============================================================================

class KGNode(BaseModel):
    """A node entity in the oncology knowledge graph."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    node_type: KGNodeType
    external_id: str
    name: str
    display_label: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KGEdge(BaseModel):
    """
    A directed relationship connecting two nodes in the oncology knowledge graph,
    enforcing complete provenance and evidence lineage.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_node_id: UUID
    relationship_type: KGRelationshipType
    target_node_id: UUID
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    properties: Dict[str, Any] = Field(default_factory=dict)
    evidence_lineage: List[EdgeEvidenceProvenance] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 4. Graph Query Output Models
# ==============================================================================

class GraphNodeSummary(BaseModel):
    node_id: UUID
    node_type: KGNodeType
    name: str
    display_label: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphEdgeSummary(BaseModel):
    edge_id: UUID
    relationship_type: KGRelationshipType
    source_id: UUID
    target_id: UUID
    confidence: float
    evidence_count: int
    primary_citation: str = ""


class GraphPathMatch(BaseModel):
    asset_id: UUID
    asset_name: str
    matched_nodes: List[GraphNodeSummary]
    evidence_lineage: List[EdgeEvidenceProvenance]
    explanation: str


class OncologyGraphQueryResult(BaseModel):
    question_id: int
    question_text: str
    matched_assets_count: int
    matches: List[GraphPathMatch]
    queried_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
