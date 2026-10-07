from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.opportunity_engine.domain.canonical_model import (
    EvidencePolarity,
    ScientificEvidenceState,
    StrategicAction,
)
from app.opportunity_engine.temporal.models import EvidenceTemporalMetadata


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
    limitations: List[str] = Field(default_factory=list)


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
    peer_review_status: Optional[str] = None
    prospective_or_retrospective: ProspectiveOrRetrospective = ProspectiveOrRetrospective.NOT_APPLICABLE
    quality_score: float = Field(ge=0.0, le=100.0, default=85.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    temporal_validity: EvidenceTemporalScope
    temporal_metadata: Optional[EvidenceTemporalMetadata] = None
    quality: Optional[EvidenceQuality] = None
    confidence_details: Optional[EvidenceConfidence] = None
    citation: Optional[EvidenceCitation] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="before")
    @classmethod
    def populate_source_temporal_metadata(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "temporal_metadata" not in data or data["temporal_metadata"] is None:
            pub_date = data.get("publication_date")
            src_type = data.get("source_type")
            trial_date = pub_date if src_type in [SourceType.CLINICAL_TRIAL, "clinical_trial"] else None
            reg_date = pub_date if src_type in [SourceType.REGULATORY_SOURCE, "regulatory_source"] else None
            lic_date = pub_date if src_type in [SourceType.COMPANY_SOURCE, "company_source"] else None
            data["temporal_metadata"] = EvidenceTemporalMetadata(
                publication_date=pub_date,
                trial_date=trial_date,
                regulatory_date=reg_date,
                licensing_date=lic_date,
                public_availability_date=pub_date,
            )
        return data


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
    evidence/source reference, source location, extracted text/value, normalized value, unit,
    entity, date, extraction method, confidence.
    Every observation must reference its evidence via evidence_id.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    evidence_id: UUID = Field(default_factory=uuid4)
    extraction_id: Optional[UUID] = None
    source_id: UUID = Field(default_factory=uuid4)
    source_ref: str = ""
    asset_id: UUID
    entity: str = ""
    parameter_name: str
    extracted_text_or_value: str = ""
    observed_value: str = ""
    normalized_value: float = 0.0
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    observation_date: date = Field(default_factory=date.today)
    source_location: str = ""
    statistical_significance: Optional[str] = None
    extraction_method: ExtractionMethod = ExtractionMethod.LLM_STRUCTURED_EXTRACTION
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    observation_state: ScientificEvidenceState = ScientificEvidenceState.VERIFIED_FACT
    temporal_metadata: Optional[EvidenceTemporalMetadata] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="before")
    @classmethod
    def sync_observation_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Ensure evidence_id and source_id are in sync
        if "evidence_id" not in data or data["evidence_id"] is None:
            if "source_id" in data and data["source_id"] is not None:
                data["evidence_id"] = data["source_id"]
            else:
                data["evidence_id"] = uuid4()
        if "source_id" not in data or data["source_id"] is None:
            data["source_id"] = data["evidence_id"]

        # Ensure extracted_text_or_value and observed_value are in sync
        if "observed_value" in data and ("extracted_text_or_value" not in data or not data["extracted_text_or_value"]):
            data["extracted_text_or_value"] = str(data["observed_value"])
        elif "extracted_text_or_value" in data and ("observed_value" not in data or not data["observed_value"]):
            data["observed_value"] = str(data["extracted_text_or_value"])

        # Populate temporal_metadata
        if "temporal_metadata" not in data or data["temporal_metadata"] is None:
            obs_date = data.get("observation_date") or date.today()
            data["temporal_metadata"] = EvidenceTemporalMetadata(
                observation_date=obs_date,
                public_availability_date=obs_date,
            )

        # Ensure numeric_value and normalized_value are in sync
        if "numeric_value" in data and data["numeric_value"] is not None and "normalized_value" not in data:
            data["normalized_value"] = float(data["numeric_value"])
        elif "normalized_value" in data and data["normalized_value"] is not None and "numeric_value" not in data:
            data["numeric_value"] = float(data["normalized_value"])

        return data


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
    citations, extractions, observations, and claims.
    Captures all 16 evidence requirements:
    source_type, source_id, title, authors, organization, publication_date,
    retrieval_date, study_type, phase, species, model, sample_size,
    peer_reviewed / peer_review_status, prospective_or_retrospective,
    quality, confidence.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    source_type: SourceType = SourceType.PUBLICATION
    source_id: str = ""
    title: str = ""
    authors: List[str] = Field(default_factory=list)
    organization: str = ""
    publication_date: Optional[date] = None
    retrieval_date: Optional[date] = None
    url_reference: str = ""
    study_type: str = "interventional_trial"
    phase: Optional[str] = None
    species: Optional[str] = "Human"
    model: Optional[str] = None
    sample_size: Optional[int] = None
    peer_reviewed: bool = True
    peer_review_status: Optional[str] = None
    prospective_or_retrospective: ProspectiveOrRetrospective = ProspectiveOrRetrospective.NOT_APPLICABLE
    quality_score: float = Field(ge=0.0, le=100.0, default=85.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.90)
    temporal_validity: Optional[EvidenceTemporalScope] = None
    temporal_metadata: Optional[EvidenceTemporalMetadata] = None
    quality: Optional[EvidenceQuality] = None
    confidence_details: Optional[EvidenceConfidence] = None
    citation: Optional[EvidenceCitation] = None
    extractions: List[EvidenceExtraction] = Field(default_factory=list)
    observations: List[EvidenceObservation] = Field(default_factory=list)
    claims: List[EvidenceClaim] = Field(default_factory=list)

    # Legacy & relational foreign keys for backwards compatibility
    publication_id: Optional[UUID] = None
    trial_id: Optional[UUID] = None
    evidence_type: str = "literature"
    source_ref: str = ""
    publication_year: int = 2024
    as_of_date: Optional[date] = None
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    is_verified: bool = True
    excerpt: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="before")
    @classmethod
    def sync_evidence_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "publication_date" in data and data["publication_date"] is not None:
            pub_date = data["publication_date"]
            if hasattr(pub_date, "year"):
                data.setdefault("publication_year", pub_date.year)
                data.setdefault("as_of_date", pub_date)
        elif "as_of_date" in data and data["as_of_date"] is not None:
            data.setdefault("publication_date", data["as_of_date"])
            if hasattr(data["as_of_date"], "year"):
                data.setdefault("publication_year", data["as_of_date"].year)

        if "temporal_metadata" not in data or data["temporal_metadata"] is None:
            pub_date = data.get("publication_date") or data.get("as_of_date")
            src_type = data.get("source_type")
            trial_date = pub_date if src_type in [SourceType.CLINICAL_TRIAL, "clinical_trial"] else None
            reg_date = pub_date if src_type in [SourceType.REGULATORY_SOURCE, "regulatory_source"] else None
            lic_date = pub_date if src_type in [SourceType.COMPANY_SOURCE, "company_source"] else None
            data["temporal_metadata"] = EvidenceTemporalMetadata(
                publication_date=pub_date,
                trial_date=trial_date,
                regulatory_date=reg_date,
                licensing_date=lic_date,
                public_availability_date=pub_date,
            )
        if "title" in data and data["title"] and not data.get("excerpt"):
            data["excerpt"] = data["title"]
        elif "excerpt" in data and data["excerpt"] and not data.get("title"):
            data["title"] = data["excerpt"]
        if "source_id" in data and data["source_id"] and not data.get("source_ref"):
            data["source_ref"] = data["source_id"]
        elif "source_ref" in data and data["source_ref"] and not data.get("source_id"):
            data["source_id"] = data["source_ref"]
        if "peer_review_status" in data and data["peer_review_status"]:
            data.setdefault("peer_reviewed", data["peer_review_status"] == "peer_reviewed")
        elif "peer_reviewed" in data:
            data.setdefault("peer_review_status", "peer_reviewed" if data["peer_reviewed"] else "not_peer_reviewed")
        if "citation" in data and isinstance(data["citation"], str):
            citation_str = data["citation"]
            data["citation"] = {
                "source_id": data.get("id") or uuid4(),
                "formatted_citation": citation_str,
                "short_citation": citation_str[:50],
            }
        return data


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
