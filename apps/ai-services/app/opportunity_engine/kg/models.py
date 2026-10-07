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

    # Canonical 15 directional aliases (Asset -> Entity)
    ASSET_TO_TARGET = "TARGETS"
    ASSET_TO_GENE = "INVOLVES_GENE"
    ASSET_TO_MUTATION = "HARBORS_MUTATION"
    ASSET_TO_DISEASE = "TREATS_DISEASE"
    ASSET_TO_BIOMARKER = "STRATIFIED_BY_BIOMARKER"
    ASSET_TO_PATIENT_POPULATION = "ENROLLS_POPULATION"
    ASSET_TO_TRIAL = "EVALUATED_IN_TRIAL"
    ASSET_TO_PUBLICATION = "REPORTED_IN_PUB"
    ASSET_TO_COMPANY = "DEVELOPED_BY_COMPANY"
    ASSET_TO_COMPETITOR = "COMPETES_WITH"
    ASSET_TO_RESISTANCE = "ACQUIRES_RESISTANCE"
    ASSET_TO_COMBINATION = "OVERCOMES_RESISTANCE_VIA"
    ASSET_TO_PATENT = "COVERED_BY_PATENT"
    ASSET_TO_LICENSE = "SUBJECT_TO_LICENSE"
    ASSET_TO_REGULATORY_EVENT = "GOVERNED_BY_REGULATORY_EVENT"


class MissingEvidenceProvenanceError(ValueError):
    """Raised when an edge or relationship is created without evidence provenance."""
    pass


CANONICAL_ONCOLOGY_RELATIONSHIPS: List[str] = [
    "Asset → Target",
    "Asset → Gene",
    "Asset → Mutation",
    "Asset → Disease",
    "Asset → Biomarker",
    "Asset → Patient Population",
    "Asset → Trial",
    "Asset → Publication",
    "Asset → Company",
    "Asset → Competitor",
    "Asset → Resistance",
    "Asset → Combination",
    "Asset → Patent",
    "Asset → License",
    "Asset → Regulatory Event",
]

CANONICAL_RELATIONSHIP_CATEGORY_MAP: Dict[str, KGRelationshipType] = {
    "target": KGRelationshipType.TARGETS,
    "gene": KGRelationshipType.INVOLVES_GENE,
    "mutation": KGRelationshipType.HARBORS_MUTATION,
    "disease": KGRelationshipType.TREATS_DISEASE,
    "biomarker": KGRelationshipType.STRATIFIED_BY_BIOMARKER,
    "patient_population": KGRelationshipType.ENROLLS_POPULATION,
    "trial": KGRelationshipType.EVALUATED_IN_TRIAL,
    "publication": KGRelationshipType.REPORTED_IN_PUB,
    "company": KGRelationshipType.DEVELOPED_BY_COMPANY,
    "competitor": KGRelationshipType.COMPETES_WITH,
    "resistance": KGRelationshipType.ACQUIRES_RESISTANCE,
    "combination": KGRelationshipType.OVERCOMES_RESISTANCE_VIA,
    "patent": KGRelationshipType.COVERED_BY_PATENT,
    "license": KGRelationshipType.SUBJECT_TO_LICENSE,
    "regulatory_event": KGRelationshipType.GOVERNED_BY_REGULATORY_EVENT,
}


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


class RelationshipProvenanceDetail(BaseModel):
    """
    Granular relationship record with verified evidence provenance.
    """
    model_config = ConfigDict(from_attributes=True)

    edge_id: UUID
    relationship_type: KGRelationshipType
    relationship_category: str
    source_node: GraphNodeSummary
    target_node: GraphNodeSummary
    confidence: float
    properties: Dict[str, Any] = Field(default_factory=dict)
    evidence_lineage: List[EdgeEvidenceProvenance] = Field(default_factory=list)


class AssetOpportunityGraph(BaseModel):
    """
    Comprehensive Oncology Opportunity Graph for an asset covering all 15
    biomedical and competitive relationships with complete evidence provenance.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    asset_name: str
    total_relationships: int
    relationships_by_category: Dict[str, List[RelationshipProvenanceDetail]] = Field(default_factory=dict)
    covered_categories: List[str] = Field(default_factory=list)
    all_relationships_have_provenance: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateEdgeRequest(BaseModel):
    """Payload for creating a new directed edge in the knowledge graph."""
    source_node_id: UUID
    relationship_type: KGRelationshipType
    target_node_id: UUID
    evidence_lineage: List[EdgeEvidenceProvenance] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    properties: Dict[str, Any] = Field(default_factory=dict)

