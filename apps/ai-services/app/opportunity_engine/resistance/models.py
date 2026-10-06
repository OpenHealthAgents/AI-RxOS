from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

RESISTANCE_INTELLIGENCE_DISCLAIMER = (
    "Never present predicted resistance as experimentally proven resistance. "
    "Predicted mechanisms represent hypothesis-generation for prospective surveillance."
)


# ==============================================================================
# 1. Enums
# ==============================================================================

class ResistanceCategory(str, Enum):
    TARGET_MUTATION = "target mutation"
    TARGET_AMPLIFICATION = "target amplification"
    BYPASS_SIGNALING = "bypass signaling"
    DOWNSTREAM_ACTIVATION = "downstream activation"
    PATHWAY_ADAPTATION = "pathway adaptation"
    PHENOTYPIC_ESCAPE = "phenotypic escape"
    TUMOR_MICROENVIRONMENT = "tumor microenvironment mechanisms"
    METABOLIC_ADAPTATION = "metabolic adaptation"


class ResistanceClassification(str, Enum):
    CLINICALLY_OBSERVED = "Clinically observed"
    OBSERVED = "Observed"
    PRECLINICAL = "Preclinical"
    MECHANISTICALLY_INFERRED = "Mechanistically inferred"
    AI_PREDICTED = "AI-predicted"


class ResistanceRiskTier(str, Enum):
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class ImpactSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


# ==============================================================================
# 2. Interventions & Escape Mechanisms
# ==============================================================================

class PotentialIntervention(BaseModel):
    """
    Actionable combination strategy, next-generation inhibitor switch,
    or prophylactic regimen to preempt or overcome drug resistance.
    """
    model_config = ConfigDict(from_attributes=True)

    strategy_type: str = Field(description="e.g. COMBINATION_CO_TARGETING, NEXT_GEN_SWITCH, PROPHYLAXIS, SEQUENTIAL_THERAPY")
    intervention_name: str = Field(description="e.g. + Fulvestrant, T-DXd (HER2 ADC), + Capivasertib (AKT inhibitor)")
    target_mechanism: str = Field(description="Escape mechanism being intercepted")
    mechanistic_rationale: str
    development_status: str = Field(description="e.g. FDA Approved SOC, Phase 2 trial, Preclinical proof of concept")
    feasibility_score: float = Field(ge=0.0, le=1.0, description="Clinical feasibility and safety score")
    citations: List[str] = Field(default_factory=list)


class EscapeMechanism(BaseModel):
    """
    Individual molecular or cellular resistance escape mechanism.
    Strict Invariant:
    Never present predicted resistance as experimentally proven resistance.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    mechanism_name: str
    category: ResistanceCategory
    classification: ResistanceClassification
    is_known_mechanism: bool = Field(default=True, description="Known vs predicted mechanism")
    is_experimentally_proven: bool = Field(default=False, description="True ONLY for Clinically observed, Observed, or Preclinical")
    frequency_pct: Optional[float] = Field(default=None, description="Observed or estimated frequency percentage in resistant cohort")
    impact_severity: ImpactSeverity
    molecular_description: str
    potential_intervention: PotentialIntervention
    evidence_citations: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, description="Evidence certainty score")
    epistemic_status_note: str

    @model_validator(mode="after")
    def verify_epistemic_integrity(self) -> EscapeMechanism:
        """
        Enforce Strict Invariant:
        Predicted or mechanistically inferred resistance can never be presented as experimentally proven.
        """
        unproven_classifications = {
            ResistanceClassification.AI_PREDICTED,
            ResistanceClassification.MECHANISTICALLY_INFERRED,
        }
        if self.classification in unproven_classifications and self.is_experimentally_proven:
            raise ValueError(
                f"Epistemic Invariant Violation: Mechanism '{self.mechanism_name}' is classified as "
                f"'{self.classification.value}', but marked as experimentally proven. "
                "Never present predicted resistance as experimentally proven resistance."
            )
        return self


# ==============================================================================
# 3. Comprehensive Resistance Risk Profile
# ==============================================================================

class ResistanceRiskProfile(BaseModel):
    """
    Composite resistance risk profile for an oncology therapeutic asset.
    Answers:
    - What is the overall resistance risk and primary vulnerability?
    - What are the top escape mechanisms across categories?
    - What is the evidence grounding each escape pathway?
    - What actionable interventions can overcome resistance?
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str
    overall_risk_score: float = Field(ge=0.0, le=100.0, description="Composite resistance susceptibility score")
    risk_tier: ResistanceRiskTier
    primary_vulnerability: str
    top_escape_mechanisms: List[EscapeMechanism]
    mechanisms_by_category: Dict[str, List[EscapeMechanism]] = Field(default_factory=dict)
    evidence_summary: str
    overall_confidence: float = Field(ge=0.0, le=1.0)
    recommended_interventions: List[PotentialIntervention] = Field(default_factory=list)
    epistemic_audit: Dict[str, Any] = Field(
        default_factory=dict,
        description="Epistemic validation audit separating experimentally proven vs predicted mechanisms",
    )
    disclaimer: str = Field(default=RESISTANCE_INTELLIGENCE_DISCLAIMER)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 4. Evaluation Request & Comparison Models
# ==============================================================================

class EvaluateResistanceRequest(BaseModel):
    asset_id: str
    include_ai_predicted: bool = Field(default=True)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ResistanceInterventionComparison(BaseModel):
    asset_id: str
    escape_mechanism_id: str
    escape_mechanism_name: str
    category: ResistanceCategory
    interventions: List[PotentialIntervention]
    preferred_intervention: PotentialIntervention
