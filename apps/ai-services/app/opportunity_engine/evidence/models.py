from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.domain.canonical_model import (
    EvidencePolarity,
    ScientificEvidenceState,
    StrategicAction,
)


class SourceType(str, Enum):
    PUBLICATION = "publication"
    CLINICAL_TRIAL = "clinical_trial"
    REGULATORY_SOURCE = "regulatory_source"
    PATENT = "patent"
    COMPANY_SOURCE = "company_source"
    CONFERENCE_ABSTRACT = "conference_abstract"
    SCIENTIFIC_DATABASE = "scientific_database"
    INSTITUTIONAL_SOURCE = "institutional_source"


class ProspectiveOrRetrospective(str, Enum):
    PROSPECTIVE = "prospective"
    RETROSPECTIVE = "retrospective"
    NOT_APPLICABLE = "not_applicable"


class ExtractionMethod(str, Enum):
    LLM_STRUCTURED_EXTRACTION = "llm_structured_extraction"
    REGEX_PIPELINE = "regex_pipeline"
    CURATED_EXPERT = "curated_expert"
    OCR_TABLE_PARSER = "ocr_table_parser"


class RiskOfBias(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNCLEAR = "unclear"


class QualityGrade(str, Enum):
    GRADE_A_HIGH = "GRADE_A_HIGH"
    GRADE_B_MODERATE = "GRADE_B_MODERATE"
    GRADE_C_LOW = "GRADE_C_LOW"
    GRADE_D_VERY_LOW = "GRADE_D_VERY_LOW"


class ConfidenceLevel(str, Enum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class ClaimType(str, Enum):
    EFFICACY = "efficacy"
    SELECTIVITY = "selectivity"
    SAFETY_TOLERABILITY = "safety_tolerability"
    CNS_PENETRATION = "cns_penetration"
    RESISTANCE_RISK = "resistance_risk"
    COMMERCIAL_FTO = "commercial_fto"


class LineageStep(str, Enum):
    SOURCE_TO_EXTRACTION = "source_to_extraction"
    EXTRACTION_TO_OBSERVATION = "extraction_to_observation"
    OBSERVATION_TO_CLAIM = "observation_to_claim"
    OBSERVATION_TO_FEATURE = "observation_to_feature"
    FEATURE_TO_MODEL_OUTPUT = "feature_to_model_output"
    MODEL_OUTPUT_TO_RECOMMENDATION = "model_output_to_recommendation"


class RelationshipType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVES_INTO = "derives_into"
    CALIBRATES = "calibrates"
    CONTEXTUALIZES = "contextualizes"
    REBUTS = "rebuts"


# ==============================================================================
# Temporal Scope, Quality & Confidence
# ==============================================================================

class EvidenceTemporalScope(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    valid_from: date
    valid_to: Optional[date] = None
    as_of_date: date
    is_current: bool = True
    cutoff_compliant: bool = True


class EvidenceQuality(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    quality_score: float = Field(ge=0.0, le=100.0, default=85.0)
    methodological_rigor: float = Field(ge=0.0, le=100.0, default=85.0)
    risk_of_bias: RiskOfBias = RiskOfBias.LOW
    reproducibility_flag: bool = True
    quality_grade: QualityGrade = QualityGrade.GRADE_A_HIGH
    scoring_breakdown: Dict[str, float] = Field(default_factory=dict)


class EvidenceConfidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    score: float = Field(ge=0.0, le=1.0, default=0.90)
    confidence_interval_low: Optional[float] = None
    confidence_interval_high: Optional[float] = None
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH
    epistemic_uncertainty: float = Field(ge=0.0, le=1.0, default=0.10)
    aleatoric_uncertainty: float = Field(ge=0.0, le=1.0, default=0.05)
    calibration_notes: Optional[str] = None


# ==============================================================================
# Citations & Sources
# ==============================================================================

class EvidenceCitation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    formatted_citation: str
    short_citation: str
    doi: Optional[str] = None
    pmid: Optional[str] = None
    nct_id: Optional[str] = None
    patent_number: Optional[str] = None
    url: Optional[str] = None
    citation_style: str = "vancouver"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceSource(BaseModel):
    """
    Provenance source capturing all 18 evidence requirements.
    Supports: publication, clinical trial, regulatory source, patent, company source,
    conference abstract, scientific database, institutional source.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_type: SourceType
    source_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    organization: str
    publication_date: date
    retrieval_date: date
    url_reference: str
    study_type: str
    phase: Optional[str] = None
    species: Optional[str] = "Human"
    model: Optional[str] = None
    sample_size: Optional[int] = None
    peer_reviewed: bool = True
    prospective_or_retrospective: ProspectiveOrRetrospective = ProspectiveOrRetrospective.NOT_APPLICABLE
    quality_score: float = Field(ge=0.0, le=100.0, default=85.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    temporal_validity: EvidenceTemporalScope
    quality: Optional[EvidenceQuality] = None
    confidence_details: Optional[EvidenceConfidence] = None
    citation: Optional[EvidenceCitation] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# Extractions & Observations
# ==============================================================================

class EvidenceExtraction(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    source_location: str
    extracted_text: str
    extraction_method: ExtractionMethod = ExtractionMethod.LLM_STRUCTURED_EXTRACTION
    extractor_model: Optional[str] = "DeepMind-BioExtractor-v2"
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    extracted_date: date
    validation_status: str = "validated"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceObservation(BaseModel):
    """
    Extracted observation retaining:
    source, source location, extracted text/value, normalized value, unit,
    entity, date, extraction method, confidence.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    extraction_id: Optional[UUID] = None
    source_id: UUID
    source_ref: str
    asset_id: UUID
    entity: str
    parameter_name: str
    extracted_text_or_value: str
    normalized_value: float
    unit: Optional[str] = None
    observation_date: date
    source_location: str
    extraction_method: ExtractionMethod = ExtractionMethod.LLM_STRUCTURED_EXTRACTION
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    observation_state: ScientificEvidenceState = ScientificEvidenceState.VERIFIED_FACT
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# Claims & Relationships
# ==============================================================================

class EvidenceClaim(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    claim_text: str
    claim_type: ClaimType
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    epistemic_status: ScientificEvidenceState = ScientificEvidenceState.VERIFIED_FACT
    supporting_observation_ids: List[UUID] = Field(default_factory=list)
    contradicting_observation_ids: List[UUID] = Field(default_factory=list)
    synthesis_confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceRelationship(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    source_entity_id: UUID
    source_entity_type: str
    target_entity_id: UUID
    target_entity_type: str
    relationship_type: RelationshipType
    lineage_step: LineageStep
    weight: float = Field(ge=0.0, le=1.0, default=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# Lineage Pipeline Nodes (Features, Model Outputs, Recommendations)
# ==============================================================================

class DerivedFeature(BaseModel):
    """
    Intermediate feature calculated deterministically from normalized observations.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    feature_name: str
    computed_value: float
    calculation_formula: str
    formula_version: str = "v1.0"
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    source_observation_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ModelOutput(BaseModel):
    """
    Output produced by predictive / utility models from derived features.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    model_name: str
    model_version: str = "v0.1"
    output_metric: str
    output_value: float
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    derived_feature_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RecommendationLineage(BaseModel):
    """
    Provenance connection linking a final strategic decision/recommendation
    to its contributing model outputs and underlying evidence.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    recommendation_id: UUID
    model_output_id: UUID
    asset_id: UUID
    action: StrategicAction
    lineage_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# Aggregate Evidence Model
# ==============================================================================

class Evidence(BaseModel):
    """
    Aggregate Evidence record encapsulating source provenance, quality,
    citations, extractions, and observations.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    source_type: SourceType
    source_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    organization: str
    publication_date: date
    retrieval_date: date
    url_reference: str
    study_type: str
    phase: Optional[str] = None
    species: Optional[str] = "Human"
    model: Optional[str] = None
    sample_size: Optional[int] = None
    peer_reviewed: bool = True
    prospective_or_retrospective: ProspectiveOrRetrospective = ProspectiveOrRetrospective.NOT_APPLICABLE
    quality_score: float = Field(ge=0.0, le=100.0, default=85.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    temporal_validity: EvidenceTemporalScope
    quality: EvidenceQuality
    confidence_details: EvidenceConfidence
    citation: EvidenceCitation
    extractions: List[EvidenceExtraction] = Field(default_factory=list)
    observations: List[EvidenceObservation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceLineageGraph(BaseModel):
    """
    Complete Directed Acyclic Graph (DAG) tracing from raw sources
    down to final recommendations.
    """
    model_config = ConfigDict(from_attributes=True)
    recommendation_id: UUID
    asset_id: UUID
    sources: List[EvidenceSource] = Field(default_factory=list)
    extractions: List[EvidenceExtraction] = Field(default_factory=list)
    observations: List[EvidenceObservation] = Field(default_factory=list)
    derived_features: List[DerivedFeature] = Field(default_factory=list)
    model_outputs: List[ModelOutput] = Field(default_factory=list)
    relationships: List[EvidenceRelationship] = Field(default_factory=list)
    is_lineage_complete: bool = True
    orphaned_components: List[str] = Field(default_factory=list)
