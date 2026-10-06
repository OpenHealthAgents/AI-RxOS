from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

COMBINATION_INTELLIGENCE_DISCLAIMER = (
    "Never present an AI-generated hypothesis or mechanistically plausible combination "
    "as clinically validated. Clinical safety, pharmacokinetic tolerability, and antitumor "
    "efficacy must be verified empirically through dedicated clinical trials."
)


# ==============================================================================
# 1. Epistemic Validation & Risk Enums
# ==============================================================================

class CombinationValidationStatus(str, Enum):
    CLINICALLY_VALIDATED = "clinically validated"
    PRECLINICAL_SUPPORTED = "preclinical supported"
    MECHANISTICALLY_PLAUSIBLE = "mechanistically plausible"
    AI_GENERATED_HYPOTHESIS = "AI-generated hypothesis"


class DevelopmentRiskTier(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ToxicityOverlapSeverity(str, Enum):
    MINIMAL = "MINIMAL"
    MANAGEABLE = "MANAGEABLE"
    SIGNIFICANT = "SIGNIFICANT"
    SEVERE = "SEVERE"


# ==============================================================================
# 2. Evaluation Sub-Models (8 Core Dimensions)
# ==============================================================================

class MechanisticComplementarityEvaluation(BaseModel):
    """
    Evaluates how the partner molecule biologically complements the index asset
    by interrupting bypass loops, vertical cascades, or reciprocal reactivation.
    """
    model_config = ConfigDict(from_attributes=True)

    synergy_mechanism: str = Field(description="e.g. Vertical dual-nodal pathway blockade, Collateral bypass interception, Feedback loop suppression")
    biological_rationale: str
    pathway_target: str
    escape_suppression_mode: str


class PreclinicalEvidenceEvaluation(BaseModel):
    """
    In vitro synergy metrics, combination index (CI), and in vivo animal models.
    """
    model_config = ConfigDict(from_attributes=True)

    in_vitro_synergy: Optional[str] = Field(default=None, description="e.g. Bliss excess score 0.28 (synergistic), Loewe CI = 0.45")
    in_vivo_models: List[str] = Field(default_factory=list, description="e.g. CDX xenograft, PDX mutant breast cancer model")
    tumor_growth_inhibition_pct: Optional[float] = Field(default=None, description="Reported TGI percentage in combination vs monotherapy")
    summary: str


class ClinicalEvidenceEvaluation(BaseModel):
    """
    Clinical trial evidence from early basket to randomized Phase 3 trials.
    """
    model_config = ConfigDict(from_attributes=True)

    trial_phase: Optional[str] = Field(default=None, description="e.g. Phase 3 Randomized, Phase 1b/2 Basket, Approved SOC")
    nct_id: Optional[str] = None
    reported_orr_pct: Optional[float] = None
    reported_pfs_months: Optional[float] = None
    summary: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)


class ToxicityOverlapEvaluation(BaseModel):
    """
    Evaluates adverse event overlap, synergistic toxicities, and dose reduction risks.
    """
    model_config = ConfigDict(from_attributes=True)

    overlap_severity: ToxicityOverlapSeverity
    shared_adverse_events: List[str] = Field(default_factory=list, description="e.g. Diarrhea, Neutropenia, Hyperglycemia, Rash")
    dose_limiting_toxicities: List[str] = Field(default_factory=list)
    therapeutic_window_impact: str
    mitigation_strategy: str


class PharmacologicalFeasibilityEvaluation(BaseModel):
    """
    PK/PD compatibility, drug-drug interaction (DDI) risk, and dosing schedule alignment.
    """
    model_config = ConfigDict(from_attributes=True)

    cyp_interaction_risk: str = Field(description="CYP3A4, 2D6, 2C9 metabolic liability")
    efflux_interaction: str = Field(description="P-gp / BCRP transporter overlap")
    schedule_compatibility: str = Field(description="e.g. Once-daily oral + monthly intramuscular injection")
    pk_ddi_score: float = Field(ge=0.0, le=1.0, description="1.0 = Clean PK, 0.0 = Severe DDI contraindication")


class DevelopmentFeasibilityEvaluation(BaseModel):
    """
    Regulatory precedent, corporate IP / licensing freedom, and single-sponsor feasibility.
    """
    model_config = ConfigDict(from_attributes=True)

    sponsor_landscape: str = Field(description="Single-sponsor proprietary, generic partner, or co-development required")
    regulatory_pathway: str = Field(description="FDA Project Optimus compliance, Fast Track precedent, Breakthrough potential")
    ip_freedom: str = Field(description="Partner generic availability or combination patentability")
    feasibility_score: float = Field(ge=0.0, le=1.0)


class ExistingCombinationReference(BaseModel):
    """
    Existing approved combinations or trials in this or related oncologic settings.
    """
    model_config = ConfigDict(from_attributes=True)

    regimen_name: str
    indication: str
    status: str = Field(description="e.g. FDA Approved SOC, Active Phase 2, Completed")
    reference: str


class CompetitiveCombinationReference(BaseModel):
    """
    Rival combination regimens pursued by competitors addressing the same biology.
    """
    model_config = ConfigDict(from_attributes=True)

    competitor_name: str
    competing_regimen: str
    phase: str
    differentiation: str


# ==============================================================================
# 3. Recommended Combination Strategy Model
# ==============================================================================

class RecommendedCombinationStrategy(BaseModel):
    """
    Comprehensive combination recommendation addressing a specific resistance mechanism.
    Evaluates all 8 core dimensions and enforces strict epistemic integrity.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    regimen_name: str = Field(description="e.g. Zongertinib + Fulvestrant, Tucatinib + T-DXd")
    primary_asset_id: str
    primary_asset_name: str
    partner_name: str
    partner_class: str = Field(description="e.g. Selective Estrogen Receptor Degrader (SERD), Antibody-Drug Conjugate (ADC)")
    resistance_mechanism_addressed: str
    resistance_category: str

    # Epistemic Validation Status
    validation_status: CombinationValidationStatus
    is_clinically_validated: bool = Field(default=False)

    # 8 Evaluation Dimensions
    mechanistic_complementarity: MechanisticComplementarityEvaluation
    preclinical_evidence: PreclinicalEvidenceEvaluation
    clinical_evidence: ClinicalEvidenceEvaluation
    toxicity_overlap: ToxicityOverlapEvaluation
    pharmacological_feasibility: PharmacologicalFeasibilityEvaluation
    development_feasibility: DevelopmentFeasibilityEvaluation
    existing_combinations: List[ExistingCombinationReference] = Field(default_factory=list)
    competitive_combinations: List[CompetitiveCombinationReference] = Field(default_factory=list)

    # Synthesis Outputs
    rationale: str
    evidence_citations: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    development_risk_score: float = Field(ge=0.0, le=100.0)
    development_risk_tier: DevelopmentRiskTier
    epistemic_disclaimer: str = Field(default=COMBINATION_INTELLIGENCE_DISCLAIMER)

    @model_validator(mode="after")
    def enforce_epistemic_integrity(self) -> RecommendedCombinationStrategy:
        """
        Enforce Strict Invariant:
        Clearly distinguish clinically validated, preclinical supported, mechanistically plausible,
        and AI-generated hypotheses. Never present an AI-generated hypothesis or mechanistically
        plausible combination as clinically validated.
        """
        unvalidated = {
            CombinationValidationStatus.AI_GENERATED_HYPOTHESIS,
            CombinationValidationStatus.MECHANISTICALLY_PLAUSIBLE,
        }
        if self.validation_status in unvalidated and self.is_clinically_validated:
            raise ValueError(
                f"Epistemic Invariant Violation: Combination '{self.regimen_name}' is classified as "
                f"'{self.validation_status.value}', but marked as clinically validated. "
                "Never present an AI-generated hypothesis or mechanistically plausible combination as clinically validated."
            )
        return self


# ==============================================================================
# 4. Composite Profile & Query Models
# ==============================================================================

class CombinationIntelligenceProfile(BaseModel):
    """
    Asset-level combination intelligence profile with ranked combinations,
    epistemic breakdown, and primary recommendation.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str
    primary_combination: RecommendedCombinationStrategy
    recommended_combinations: List[RecommendedCombinationStrategy] = Field(default_factory=list)
    epistemic_audit: Dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = Field(default=COMBINATION_INTELLIGENCE_DISCLAIMER)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvaluateCombinationQuery(BaseModel):
    asset_id: Optional[str] = None
    resistance_mechanism: Optional[str] = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    max_risk_tier: Optional[DevelopmentRiskTier] = None
    include_ai_generated: bool = Field(default=True)
