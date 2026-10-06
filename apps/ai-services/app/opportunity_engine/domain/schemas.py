from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class StrategicAction(str, Enum):
    PURSUE = "PURSUE"
    INVESTIGATE = "INVESTIGATE"
    PARTNER = "PARTNER"
    LICENSE = "LICENSE"
    MONITOR = "MONITOR"
    AVOID = "AVOID"


class DevelopmentStage(str, Enum):
    PRECLINICAL = "Preclinical"
    PHASE_I = "Phase I"
    PHASE_II = "Phase II"
    PHASE_III = "Phase III"
    APPROVED = "Approved"
    TERMINATED = "Terminated"


class ModalityType(str, Enum):
    SMALL_MOLECULE_TKI = "Small molecule TKI"
    ANTIBODY = "Monoclonal Antibody"
    ADC = "Antibody-Drug Conjugate"
    BISPECIFIC = "Bispecific Antibody"
    PROTAC = "PROTAC / Degrader"
    CELL_THERAPY = "Cell Therapy"


class EvidencePolarity(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"


class EvidenceItem(BaseModel):
    id: str
    source_type: Literal[
        "literature",
        "clinical_trial",
        "fda_label",
        "regulatory_authority",
        "patent",
        "conference_abstract",
    ]
    source_ref: str = Field(description="PMID, NCT number, FDA NDA/BLA, or Patent number")
    title: str
    citation: str
    publication_year: int
    url: Optional[str] = None
    excerpt: str
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    is_verified: bool = True
    as_of_date: str = Field(description="ISO date YYYY-MM-DD of source publication or registry date")


class StageTransitionProbabilities(BaseModel):
    preclinical_to_ind: float = Field(ge=0.0, le=1.0)
    phase_i_to_ii: float = Field(ge=0.0, le=1.0)
    phase_ii_to_iii: float = Field(ge=0.0, le=1.0)
    phase_iii_to_approval: float = Field(ge=0.0, le=1.0)
    model_version: str = "Model v0.1"
    calibration_note: str = (
        "Predictions calibrated against oncology benchmarks. Historical probabilities "
        "reflect pre-approval retrospective data."
    )


class BiologyProfileMetrics(BaseModel):
    target_selectivity: float = Field(ge=0, le=100, description="Selectivity index (WT vs mutant sparing)")
    potency: float = Field(ge=0, le=100, description="IC50 biochemical and cellular potency")
    safety_ti: float = Field(ge=0, le=100, description="Preclinical therapeutic window and GI tolerability")
    clinical_readiness: float = Field(ge=0, le=100, description="Trial stage progress and clinical disease control")
    biomarker_strategy: float = Field(ge=0, le=100, description="Defined genomic target subpopulation clarity")
    cns_potential: float = Field(ge=0, le=100, description="Intracranial/BBB penetration efficiency")


class ResistanceMechanism(BaseModel):
    name: str
    impact: Literal["High", "Moderate", "Low"]
    is_predicted: bool = Field(default=False, description="True if computational/in vitro prediction, False if clinically established")
    description: str
    evidence_ids: List[str] = Field(default_factory=list)


class RecommendedCombination(BaseModel):
    partner_name: str
    synergy_type: str
    rationale: str
    clinical_status: str
    evidence_ids: List[str] = Field(default_factory=list)


class SafetyToxicityProfile(BaseModel):
    common_aes: str
    dose_limiting_toxicities: str
    therapeutic_index: str
    discontinuation_rate: str
    cardiac_risk: Optional[str] = "Low"
    gi_toxicity_grade: Literal["Mild", "Low-Moderate", "Moderate", "High"] = "Low-Moderate"
    safety_score: float = Field(ge=0, le=100)


class PatientMatchProfile(BaseModel):
    best_patient_population: List[str]
    biomarkers: List[str]
    setting: str = "Metastatic"
    prior_lines: str = "Post-CDK4/6 or prior HER2-directed therapy"
    cns_metastases_benefit: bool = True
    match_score_formula_lineage: str = (
        "MatchScore = 0.40 * TargetExpression + 0.35 * MutationSensitivity + 0.25 * CNSPenetrationPotential"
    )


class BusinessCompetitiveProfile(BaseModel):
    current_owner: str
    patent_ip: str
    commercial_opportunity: str
    competitive_assets: str
    licensing_partnering_feasibility: str
    fto_legal_disclaimer: str = (
        "IP and licensing information is derived from public patent registries and corporate disclosures. "
        "It does not constitute formal legal opinion or Freedom to Operate (FTO) clearance."
    )


class DecisionRecommendation(BaseModel):
    action: StrategicAction
    badge_text: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    development_potential_score: int = Field(ge=0, le=100)
    development_potential_tier: Literal["Very Low", "Low", "Moderate", "High", "Very High"]
    model_lineage: str = (
        "DPS = 0.20*Selectivity + 0.15*Potency + 0.20*SafetyTI + 0.15*CNSPotential + 0.15*Biomarker + 0.15*Readiness"
    )


class UnknownFactor(BaseModel):
    id: str
    category: Literal["Clinical Efficacy", "Toxicity", "Biomarker", "IP / Licensing", "Commercial"]
    question: str
    current_gap: str
    suggested_study: str


class AssetIntelligence(BaseModel):
    id: str
    name: str
    code_name: Optional[str] = None
    target: str = "HER2"
    modality: ModalityType = ModalityType.SMALL_MOLECULE_TKI
    stage: DevelopmentStage = DevelopmentStage.PHASE_II
    status_label: Literal["Investigational", "Approved", "Preclinical", "Terminated"] = "Investigational"
    owner: str
    primary_indication: str
    key_attributes: Dict[str, str] = Field(
        description="Selectivity, IC50, Activity in mutants, CNS penetration, In vivo efficacy, Main differentiation, Current stage, Key indications"
    )
    biology_profile: BiologyProfileMetrics
    stage_transitions: StageTransitionProbabilities
    resistance_mechanisms: List[ResistanceMechanism]
    combinations: List[RecommendedCombination]
    safety_profile: SafetyToxicityProfile
    patient_match: PatientMatchProfile
    business_profile: BusinessCompetitiveProfile
    recommendation: DecisionRecommendation
    supporting_evidence: List[EvidenceItem]
    contradicting_evidence: List[EvidenceItem]
    unknowns: List[UnknownFactor]
    ai_inferences: List[str] = Field(
        default_factory=list,
        description="Explicitly declared machine learning / heuristic inference steps"
    )
    last_updated: str = "2026-10-01"


class AssetComparisonResult(BaseModel):
    target: str
    indication: str
    setting: str
    assets: List[AssetIntelligence]
    comparison_summary: str
    key_differentiators: List[str]
    head_to_head_advantages: Dict[str, List[str]]
    recommendation_summary: Dict[str, str]


class HistoricalBacktestQuery(BaseModel):
    asset_id: str
    cutoff_date: str = Field(description="Temporal cutoff ISO date YYYY-MM-DD")


class HistoricalBacktestResult(BaseModel):
    asset_id: str
    asset_name: str
    cutoff_date: str
    evidence_items_eligible: int
    evidence_items_suppressed_future: int
    predicted_action_at_cutoff: StrategicAction
    predicted_transition_probabilities: StageTransitionProbabilities
    predicted_development_potential: int
    historical_recommendation_rationale: str
    ground_truth_eventual_outcome: str
    prediction_accuracy: Literal["True Positive", "True Negative", "Calibrated Success", "Consistent Divergence"]
    anti_leakage_audit_passed: bool = True
