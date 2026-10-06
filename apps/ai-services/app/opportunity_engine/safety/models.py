from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

SAFETY_INTELLIGENCE_DISCLAIMER = (
    "Do not convert missing safety evidence into a positive score. "
    "Absence of documented toxicity evidence does not constitute safety. "
    "Preclinical or investigational molecules without human clinical safety "
    "data must be classified as INSUFFICIENT EVIDENCE."
)


# ==============================================================================
# 1. Enums
# ==============================================================================

class SafetyRating(str, Enum):
    GOOD = "GOOD"
    MODERATE = "MODERATE"
    HIGH_RISK = "HIGH RISK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT EVIDENCE"


class OrganSystem(str, Enum):
    GASTROINTESTINAL = "GASTROINTESTINAL"
    HEPATIC = "HEPATIC"
    CARDIAC = "CARDIAC"
    PULMONARY = "PULMONARY"
    DERMATOLOGIC = "DERMATOLOGIC"
    HEMATOLOGIC = "HEMATOLOGIC"
    RENAL = "RENAL"
    NEUROLOGIC = "NEUROLOGIC"


class ToxicitySeverityGrade(str, Enum):
    GRADE_1 = "Grade 1 (Mild)"
    GRADE_2 = "Grade 2 (Moderate)"
    GRADE_3 = "Grade 3 (Severe)"
    GRADE_4 = "Grade 4 (Life-threatening)"
    GRADE_5 = "Grade 5 (Fatal)"


class RiskSignalSeverity(str, Enum):
    BLACK_BOX = "BLACK_BOX"
    WARNING = "WARNING"
    WATCH = "WATCH"
    INVESTIGATIONAL = "INVESTIGATIONAL"


# ==============================================================================
# 2. Ten Core Safety Dimensions Sub-Models
# ==============================================================================

class AdverseEventRecord(BaseModel):
    """
    Structured record of an adverse event (common or Grade >=3).
    """
    model_config = ConfigDict(from_attributes=True)

    term: str
    system_organ_class: OrganSystem
    any_grade_rate_pct: float = Field(ge=0.0, le=100.0)
    grade_3_plus_rate_pct: float = Field(ge=0.0, le=100.0)
    is_dose_limiting: bool = False
    is_target_related: bool = False
    is_serious: bool = False
    clinical_description: str


class DoseLimitingToxicityEvaluation(BaseModel):
    """
    Phase 1 dose escalation DLTs, MTD, and Project Optimus RP2D determination.
    """
    model_config = ConfigDict(from_attributes=True)

    dlt_observed: bool
    dlt_terms: List[str] = Field(default_factory=list)
    maximum_tolerated_dose: Optional[str] = None
    recommended_phase_2_dose: Optional[str] = None
    project_optimus_compliant: bool
    dlt_rate_at_rp2d_pct: Optional[float] = None
    summary: str


class DiscontinuationEvaluation(BaseModel):
    """
    Treatment discontinuation, dose reduction, and dose interruption rates.
    """
    model_config = ConfigDict(from_attributes=True)

    all_cause_discontinuation_pct: float = Field(ge=0.0, le=100.0)
    ae_related_discontinuation_pct: float = Field(ge=0.0, le=100.0)
    dose_reduction_pct: float = Field(ge=0.0, le=100.0)
    dose_interruption_pct: float = Field(ge=0.0, le=100.0)
    primary_driver_terms: List[str] = Field(default_factory=list)
    tolerability_impact_summary: str


class OrganToxicityProfile(BaseModel):
    """
    Organ-specific toxicity manifestation, reversibility, and monitoring requirements.
    """
    model_config = ConfigDict(from_attributes=True)

    organ_system: OrganSystem
    severity_tier: str = Field(description="Mild, Moderate, Severe, or Dose-Limiting")
    primary_manifestations: List[str] = Field(default_factory=list)
    monitoring_requirement: str
    reversibility: str
    risk_score: float = Field(ge=0.0, le=100.0)


class TargetRelatedToxicityEvaluation(BaseModel):
    """
    On-target mechanistic toxicities vs selectivity protective windows.
    """
    model_config = ConfigDict(from_attributes=True)

    target_mechanism: str
    is_on_target_liability: bool
    selectivity_ratio_vs_offtarget: Optional[float] = Field(default=None, description="e.g. 59x selectivity over wild-type EGFR")
    selectivity_protective_effect: str
    on_target_mitigation: str


class OffTargetToxicityEvaluation(BaseModel):
    """
    Off-target promiscuity, kinase panel selectivity, hERG, and CYP liabilities.
    """
    model_config = ConfigDict(from_attributes=True)

    promiscuity_index: float = Field(ge=0.0, le=1.0, description="0.0 = clean kinase selectivity, 1.0 = pan-promiscuous")
    off_target_kinases_inhibited: List[str] = Field(default_factory=list)
    hERG_inhibition_ic50_um: Optional[float] = None
    cyp_inhibition_profile: str
    off_target_risk_summary: str


class AnimalToxicityEvaluation(BaseModel):
    """
    GLP toxicology findings in rodent and non-rodent species, NOAEL.
    """
    model_config = ConfigDict(from_attributes=True)

    species_evaluated: List[str] = Field(default_factory=list)
    noael_dose: Optional[str] = None
    target_organs_in_animals: List[str] = Field(default_factory=list)
    glp_toxicology_completed: bool
    animal_to_human_translation_note: str


class TherapeuticWindowEvaluation(BaseModel):
    """
    Exposure margin between efficacy (IC50/EC50) and toxicity threshold (MTD/NOAEL).
    """
    model_config = ConfigDict(from_attributes=True)

    therapeutic_window_ratio: float = Field(description="Ratio of toxic exposure to efficacious exposure")
    window_width: str = Field(description="Wide (>10-fold), Moderate (3-5 fold), Narrow (<2-fold), or Subtherapeutic")
    safety_margin_description: str


class DoseExposureRelationshipEvaluation(BaseModel):
    """
    PK/PD exposure-safety correlation and concentration-dependent toxicity risks.
    """
    model_config = ConfigDict(from_attributes=True)

    exposure_safety_correlation: str = Field(description="e.g. Steep Cmax-driven diarrhea, Flat AUC-tolerability profile, Linear QTc prolongation")
    concentration_dependent_dlt: bool
    pk_variability_impact: str


class MajorRiskSignal(BaseModel):
    """
    Flagged clinical safety hazards, black-box warnings, or critical organ liabilities.
    """
    model_config = ConfigDict(from_attributes=True)

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    severity: RiskSignalSeverity
    affected_organ: OrganSystem
    clinical_evidence: str
    management_recommendation: str


# ==============================================================================
# 3. Comprehensive Safety Intelligence Profile
# ==============================================================================

class SafetyIntelligenceProfile(BaseModel):
    """
    Produces:
    - Safety Score (0 - 100)
    - Therapeutic Index Score (0 - 100)
    - Safety Confidence (0.0 - 1.0)
    - Major Risk Signals
    Ratings: GOOD, MODERATE, HIGH RISK, INSUFFICIENT EVIDENCE.
    Strict Invariant: Do not convert missing safety evidence into a positive score.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str
    safety_rating: SafetyRating
    safety_score: float = Field(ge=0.0, le=100.0)
    therapeutic_index_score: float = Field(ge=0.0, le=100.0)
    safety_confidence: float = Field(ge=0.0, le=1.0)
    major_risk_signals: List[MajorRiskSignal] = Field(default_factory=list)

    # 10 Core Captured Dimensions
    common_adverse_events: List[AdverseEventRecord] = Field(default_factory=list)
    grade_3_plus_adverse_events: List[AdverseEventRecord] = Field(default_factory=list)
    dose_limiting_toxicity: DoseLimitingToxicityEvaluation
    discontinuation: DiscontinuationEvaluation
    organ_toxicities: List[OrganToxicityProfile] = Field(default_factory=list)
    target_related_toxicity: TargetRelatedToxicityEvaluation
    off_target_toxicity: OffTargetToxicityEvaluation
    animal_toxicity: AnimalToxicityEvaluation
    therapeutic_window: TherapeuticWindowEvaluation
    dose_exposure_relationship: DoseExposureRelationshipEvaluation

    # Epistemic Missing Evidence Governance
    has_missing_evidence: bool = Field(default=False)
    missing_evidence_details: List[str] = Field(default_factory=list)
    evidence_citations: List[Dict[str, Any]] = Field(default_factory=list)
    disclaimer: str = Field(default=SAFETY_INTELLIGENCE_DISCLAIMER)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def enforce_missing_evidence_invariant(self) -> SafetyIntelligenceProfile:
        """
        Enforce Strict Invariant:
        Do not convert missing safety evidence into a positive score.
        If an asset has missing safety evidence:
        - It MUST be rated INSUFFICIENT EVIDENCE
        - It CANNOT receive a safety_score > 50.0
        - It CANNOT receive a safety_rating of GOOD
        """
        if self.has_missing_evidence:
            if self.safety_rating == SafetyRating.GOOD:
                raise ValueError(
                    "Epistemic Invariant Violation: Missing safety evidence cannot be converted into a GOOD safety rating. "
                    "Assets with missing evidence must be classified as INSUFFICIENT EVIDENCE."
                )
            if self.safety_score > 50.0:
                raise ValueError(
                    f"Epistemic Invariant Violation: Safety score ({self.safety_score}) exceeds maximum allowed (50.0) "
                    "for an asset with missing safety evidence. Do not convert missing evidence into a positive score."
                )
            if self.safety_rating != SafetyRating.INSUFFICIENT_EVIDENCE:
                raise ValueError(
                    f"Epistemic Invariant Violation: Asset has missing safety evidence ({self.missing_evidence_details}) "
                    f"but was given rating '{self.safety_rating.value}'. Rating must be INSUFFICIENT EVIDENCE."
                )
        return self


# ==============================================================================
# 4. Request DTO
# ==============================================================================

class EvaluateSafetyRequest(BaseModel):
    asset_id: str
    target_indication: Optional[str] = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
