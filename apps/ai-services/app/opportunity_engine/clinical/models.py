from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 1. Enums
# ==============================================================================

class ClinicalStage(str, Enum):
    PRECLINICAL = "PRECLINICAL"
    PHASE_I = "PHASE_I"
    PHASE_IB = "PHASE_IB"
    PHASE_II = "PHASE_II"
    PHASE_II_III = "PHASE_II_III"
    PHASE_III = "PHASE_III"
    APPROVED = "APPROVED"
    TERMINATED = "TERMINATED"
    WITHDRAWN = "WITHDRAWN"
    CRL = "CRL"


class TrialDesignType(str, Enum):
    RANDOMIZED_CONTROLLED_TRIAL = "RANDOMIZED_CONTROLLED_TRIAL"
    SINGLE_ARM_BASKET = "SINGLE_ARM_BASKET"
    SINGLE_ARM_EXPANSION = "SINGLE_ARM_EXPANSION"
    OPEN_LABEL_DOSE_ESCALATION = "OPEN_LABEL_DOSE_ESCALATION"
    DOUBLE_BLIND_COMPARATOR = "DOUBLE_BLIND_COMPARATOR"
    PLATFORM_UMBRELLA = "PLATFORM_UMBRELLA"


class EndpointReviewType(str, Enum):
    BLINDED_INDEPENDENT_CENTRAL_REVIEW = "BLINDED_INDEPENDENT_CENTRAL_REVIEW"
    INVESTIGATOR_ASSESSED = "INVESTIGATOR_ASSESSED"
    LOCAL_PATHOLOGY = "LOCAL_PATHOLOGY"


class EpistemicCategory(str, Enum):
    OBSERVED_CLINICAL_OUTCOME = "OBSERVED_CLINICAL_OUTCOME"
    MODEL_PREDICTION = "MODEL_PREDICTION"
    EXPERT_INTERPRETATION = "EXPERT_INTERPRETATION"
    UNKNOWN = "UNKNOWN"


# ==============================================================================
# 2. Epistemic Separation Models
# ==============================================================================

class ObservedClinicalOutcome(BaseModel):
    """
    Empirical ground truth facts from completed or interim clinical trials.
    Includes ORR, CR, DOR, PFS, OS, clinical benefit, toxicity, discontinuation.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    trial_id: str = Field(description="e.g. NCT02614794, NCT04886804")
    trial_title: str
    phase: ClinicalStage
    sample_size: int
    population: str
    biomarker_status: str

    # Key Efficacy Endpoints
    orr_pct: Optional[float] = Field(default=None, description="Objective Response Rate (%)")
    cr_pct: Optional[float] = Field(default=None, description="Complete Response Rate (%)")
    dor_months: Optional[float] = Field(default=None, description="Median Duration of Response (months)")
    pfs_months: Optional[float] = Field(default=None, description="Median Progression-Free Survival (months)")
    pfs_hazard_ratio: Optional[float] = Field(default=None, description="PFS Hazard Ratio vs comparator")
    os_months: Optional[float] = Field(default=None, description="Median Overall Survival (months)")
    os_hazard_ratio: Optional[float] = Field(default=None, description="OS Hazard Ratio vs comparator")
    cbr_pct: Optional[float] = Field(default=None, description="Clinical Benefit Rate / Disease Control Rate (%)")

    # Safety & Tolerability
    grade_3_plus_ae_pct: Optional[float] = Field(default=None, description="Grade 3+ Adverse Event Rate (%)")
    treatment_discontinuation_pct: Optional[float] = Field(default=None, description="Discontinuation Rate due to AEs (%)")
    dose_reduction_pct: Optional[float] = Field(default=None, description="Dose Reduction Rate (%)")

    # Adjudication & Provenance
    endpoint_review: EndpointReviewType = EndpointReviewType.INVESTIGATOR_ASSESSED
    source_citation: str
    pmid: Optional[str] = None
    reported_date: Optional[date] = None


class ClinicalModelPrediction(BaseModel):
    """
    Algorithmic/statistical predictions produced by Bayesian transition
    or survival projection models.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    parameter: str = Field(description="e.g. Phase II -> III Transition, Probability of Regulatory Approval, Predicted PFS HR")
    predicted_value: float
    confidence_interval_low: Optional[float] = None
    confidence_interval_high: Optional[float] = None
    model_name: str = "Bayesian Oncology Transition Model v2.4"
    calibration_methodology: str = "Historical contemporary oncology benchmark calibrated"
    prediction_date: Optional[date] = None


class ClinicalExpertInterpretation(BaseModel):
    """
    Oncology clinician commentary, regulatory guidance consensus, or Project Optimus audit.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    topic: str = Field(description="e.g. Dose Optimization & Project Optimus, Endpoint Quality, Competitive Position")
    consensus_view: str
    regulatory_precedent: Optional[str] = None
    clinician_summary: str
    expert_source: str = "Oncology Clinical Advisory Consensus"


class TrialDesignEvaluation(BaseModel):
    """Detailed operational evaluation of clinical trial design."""
    model_config = ConfigDict(from_attributes=True)

    trial_id: str
    design_type: TrialDesignType
    enrollment_count: int
    sample_size_adequate: bool
    comparator_arm: Optional[str] = None
    blinding_method: str = "Open-Label"
    project_optimus_compliant: bool = True
    randomized_dose_optimization: bool = False
    biomarker_prospective: bool = True
    adjudication: EndpointReviewType = EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW
    execution_flags: List[str] = Field(default_factory=list)


class ClinicalScoreLineage(BaseModel):
    """Lineage formula and inputs backing every clinical development score."""
    model_config = ConfigDict(from_attributes=True)

    score_name: str
    formula: str
    inputs: Dict[str, Any]
    observed_outcome_ids: List[UUID] = Field(default_factory=list)
    calculated_value: float
    evidence_gaps: List[str] = Field(default_factory=list)


# ==============================================================================
# 3. Canonical Clinical Development Profile
# ==============================================================================

class ClinicalDevelopmentProfile(BaseModel):
    """
    Canonical Profile containing the 4 required clinical scores:
    1. Clinical Success Probability (0.0 - 1.0)
    2. Clinical Readiness Score (0 - 100)
    3. Development Risk Score (0 - 100)
    4. Evidence Confidence (0.0 - 1.0)

    Strict Epistemic Classification:
    - observed_clinical_outcomes (facts)
    - model_predictions (ML/statistical)
    - expert_interpretations (clinical commentary)
    - unknowns (evidence gaps)
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str
    stage: ClinicalStage

    # 4 Canonical Produced Scores
    clinical_success_probability: float = Field(ge=0.0, le=1.0, description="Bayesian probability of achieving regulatory approval")
    clinical_readiness_score: float = Field(ge=0.0, le=100.0, description="Maturity and operational completeness of clinical program")
    development_risk_score: float = Field(ge=0.0, le=100.0, description="Composite development liability score (higher = greater risk)")
    evidence_confidence: float = Field(ge=0.0, le=1.0, description="Statistical & methodological certainty score")

    # Evaluated Trial Designs
    trials_evaluated: List[TrialDesignEvaluation] = Field(default_factory=list)

    # 4 Strictly Separated Epistemic Collections
    observed_clinical_outcomes: List[ObservedClinicalOutcome] = Field(default_factory=list)
    model_predictions: List[ClinicalModelPrediction] = Field(default_factory=list)
    expert_interpretations: List[ClinicalExpertInterpretation] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list)

    # Mathematical Formula Lineages
    lineages: Dict[str, ClinicalScoreLineage] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 4. API Request & Response Schemas
# ==============================================================================

class EvaluateAssetClinicalRequest(BaseModel):
    asset_id: str
    asset_name: Optional[str] = None
    custom_outcomes: Optional[List[ObservedClinicalOutcome]] = None


class EvaluateAssetClinicalResponse(BaseModel):
    profile: ClinicalDevelopmentProfile
