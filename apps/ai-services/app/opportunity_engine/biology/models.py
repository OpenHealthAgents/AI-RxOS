from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.intelligence import (
    IntelligenceProfileBase,
    IntelligenceValue,
)

# ==============================================================================
# 1. Observation & Evaluation Enums
# ==============================================================================

class BiologyObservationType(str, Enum):
    IC50_BIOCHEMICAL = "IC50_BIOCHEMICAL"
    IC50_CELLULAR = "IC50_CELLULAR"
    SELECTIVITY_RATIO = "SELECTIVITY_RATIO"
    CRISPR_DEPENDENCY = "CRISPR_DEPENDENCY"
    TARGET_VALIDITY = "TARGET_VALIDITY"
    MECHANISTIC_RATIONALE = "MECHANISTIC_RATIONALE"
    ON_TARGET_ENGAGEMENT = "ON_TARGET_ENGAGEMENT"
    OFF_TARGET_RISK = "OFF_TARGET_RISK"
    BIOMARKER_STRATEGY = "BIOMARKER_STRATEGY"
    GENETIC_EVIDENCE = "GENETIC_EVIDENCE"
    FUNCTIONAL_EVIDENCE = "FUNCTIONAL_EVIDENCE"
    ANIMAL_EFFICACY = "ANIMAL_EFFICACY"
    PATIENT_DERIVED_MODELS = "PATIENT_DERIVED_MODELS"
    CLINICAL_RESPONSE = "CLINICAL_RESPONSE"


class EvaluationDimension(str, Enum):
    """The 12 biological evaluation dimensions required by the intelligence engine."""
    TARGET_VALIDITY = "target_validity"
    MECHANISTIC_RATIONALE = "mechanistic_rationale"
    POTENCY = "potency"
    SELECTIVITY = "selectivity"
    ON_TARGET_EVIDENCE = "on_target_evidence"
    OFF_TARGET_RISK = "off_target_risk"
    BIOMARKER_STRATEGY = "biomarker_strategy"
    GENETIC_EVIDENCE = "genetic_evidence"
    FUNCTIONAL_EVIDENCE = "functional_evidence"
    TRANSLATIONAL_EVIDENCE = "translational_evidence"
    MODEL_DIVERSITY = "model_diversity"
    HUMAN_EVIDENCE = "human_evidence"


class EvaluationDimensionState(str, Enum):
    VERIFIED_FACT = "VERIFIED_FACT"
    STRONG_SUPPORT = "STRONG_SUPPORT"
    MODERATE_SUPPORT = "MODERATE_SUPPORT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTRADICTORY = "CONTRADICTORY"


# ==============================================================================
# 2. Raw Observation Model
# ==============================================================================

class RawBiologicalObservation(BaseModel):
    """
    Every score must be derived from evidence.
    Raw observations capture empirical assay measurements (IC50, selectivity ratios,
    CRISPR Chronos scores, animal TGI, PDX counts, clinical ORR) before scoring.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    asset_id: str
    tenant_id: Optional[str] = None
    parameter_name: str
    observation_type: BiologyObservationType
    raw_text_value: str
    normalized_value: float
    unit: Optional[str] = None
    assay_type: Optional[str] = None
    target_or_gene: Optional[str] = None
    model_system: Optional[str] = None
    source_citation: str
    source_url: Optional[str] = None
    pmid: Optional[str] = None
    nct_id: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    observation_date: Optional[date] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 3. Dimensional Evaluation & Formula Lineage
# ==============================================================================

class DimensionEvaluation(BaseModel):
    """Evaluation summary for each of the 12 evaluation dimensions."""
    model_config = ConfigDict(from_attributes=True)

    dimension: EvaluationDimension
    state: EvaluationDimensionState
    raw_observation_ids: List[UUID] = Field(default_factory=list)
    raw_values_summary: Dict[str, Any] = Field(default_factory=dict)
    score_contribution: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    findings: str
    evidence_citations: List[str] = Field(default_factory=list)


class ScoreFormulaLineage(BaseModel):
    """
    Complete formula provenance ensuring no orphaned or manually assigned scores.
    """
    model_config = ConfigDict(from_attributes=True)

    score_name: str
    formula: str
    inputs: Dict[str, Any]
    raw_observation_ids: List[UUID] = Field(default_factory=list)
    calculated_value: float
    confidence_penalty_applied: float = 0.0
    evidence_gaps: List[str] = Field(default_factory=list)


# ==============================================================================
# 4. Canonical Biology Intelligence Profile
# ==============================================================================

class BiologyIntelligenceProfile(BaseModel):
    """
    Canonical Profile containing the 6 required biological scores:
    1. Biology Validation Score (0 - 100)
    2. Potency Score (0 - 100)
    3. Selectivity Score (0 - 100)
    4. Biomarker Score (0 - 100)
    5. Mechanistic Confidence (0.0 - 1.0)
    6. Translational Readiness (0 - 100)

    Plus evaluations across all 12 dimensions, raw observations, lineages,
    overall confidence, and explicit unknowns.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str

    # 6 Canonical Produced Scores
    biology_validation_score: float = Field(ge=0.0, le=100.0, description="Composite biological validation score")
    potency_score: float = Field(ge=0.0, le=100.0, description="Potency score calibrated from raw IC50 values")
    selectivity_score: float = Field(ge=0.0, le=100.0, description="Selectivity score from fold-selectivity ratios")
    biomarker_score: float = Field(ge=0.0, le=100.0, description="Biomarker stratification and genomic sensitivity score")
    mechanistic_confidence: float = Field(ge=0.0, le=1.0, description="Mechanistic confidence from target engagement & on-target proof")
    translational_readiness: float = Field(ge=0.0, le=100.0, description="Translational readiness from animal TGI, model diversity & human response")

    # 12 Detailed Dimensions
    dimensions: Dict[str, DimensionEvaluation] = Field(default_factory=dict)

    # Underlying Raw Observations (Provenance Lineage)
    raw_observations: List[RawBiologicalObservation] = Field(default_factory=list)

    # Explicit Mathematical Formula Lineages
    lineages: Dict[str, ScoreFormulaLineage] = Field(default_factory=dict)

    # Uncertainty & Governance
    overall_confidence: float = Field(ge=0.0, le=1.0)
    unknowns: List[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 5. API Request / Response Schemas
# ==============================================================================

class EvaluateAssetBiologyRequest(BaseModel):
    asset_id: str
    asset_name: Optional[str] = None
    custom_observations: Optional[List[RawBiologicalObservation]] = None


class EvaluateAssetBiologyResponse(BaseModel):
    profile: BiologyIntelligenceProfile


class BiologyIntelligence(IntelligenceProfileBase):
    """Cutoff-aware biology intelligence; unsupported metrics remain explicitly unknown."""

    biology_validation: IntelligenceValue
    potency: IntelligenceValue
    selectivity: IntelligenceValue
    mechanistic_confidence: IntelligenceValue
    biomarker_strength: IntelligenceValue
    translational_readiness: IntelligenceValue
