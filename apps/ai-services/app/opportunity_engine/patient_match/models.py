from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

POPULATION_INTELLIGENCE_DISCLAIMER = (
    "Do not make patient-specific medical recommendations. "
    "This is drug-development population intelligence."
)


# ==============================================================================
# 1. Enums & Recommendation Tiers
# ==============================================================================

class PopulationTier(str, Enum):
    BEST = "BEST_PATIENT_POPULATION"
    SECONDARY = "SECONDARY_PATIENT_POPULATION"
    EXCLUDED = "EXCLUDED_LOW_LIKELIHOOD_POPULATION"


# ==============================================================================
# 2. Population Recommendation & Biomarker Strategy
# ==============================================================================

class PopulationRecommendation(BaseModel):
    """
    Structured recommendation for a patient population subgroup backed by evidence.
    Captures mutation, expression, amplification, protein expression, biomarker,
    disease subtype, prior therapy, resistance state, line of therapy, CNS status,
    and clinical evidence.
    """
    model_config = ConfigDict(from_attributes=True)

    tier: PopulationTier
    name: str
    description: str
    disease_subtype: str

    # Biomarker & Molecular Criteria
    mutation: Optional[str] = Field(default=None, description="e.g. HER2 L755S, V777L, Exon 20 insertion")
    expression: Optional[str] = Field(default=None, description="e.g. ER-positive, HER2-low")
    amplification: Optional[str] = Field(default=None, description="e.g. HER2 non-amplified (FISH ratio < 2.0), HER2-amplified (IHC 3+)")
    protein_expression: Optional[str] = Field(default=None, description="e.g. ER Allred 7-8, HER2 IHC 1+")
    biomarker: str = Field(description="Primary diagnostic biomarker identifier")

    # Clinical & Cohort Criteria
    line_of_therapy: str = Field(description="e.g. 1L, 2L+, Extended Adjuvant")
    prior_therapy: List[str] = Field(default_factory=list, description="e.g. CDK4/6 inhibitor, Trastuzumab, Chemotherapy")
    resistance_state: Optional[str] = Field(default=None, description="e.g. Post-CDK4/6 progression, Anti-HER2 refractory")
    cns_status: str = Field(description="e.g. Active brain metastases, Treated/stable, or No CNS involvement")

    # Rationale & Evidence Provenance
    mechanistic_rationale: str
    evidence_summary: str
    evidence_citations: List[Dict[str, Any]] = Field(default_factory=list, description="Citations supporting population suitability")


class BiomarkerStrategy(BaseModel):
    """
    Companion diagnostic and patient selection strategy for the asset.
    """
    model_config = ConfigDict(from_attributes=True)

    primary_biomarker: str
    assay_modality: str = Field(description="e.g. NGS liquid biopsy (ctDNA), tissue panel, IHC/FISH")
    stratification_hypothesis: str
    feasibility: str
    companion_diagnostic: Optional[str] = None
    co_testing_requirements: List[str] = Field(default_factory=list)


# ==============================================================================
# 3. Canonical Asset Patient Match Profile
# ==============================================================================

class AssetPatientMatchProfile(BaseModel):
    """
    Answers: 'Which patients are most likely to benefit from this asset?'
    Exposes:
    - Best Patient Population
    - Secondary Patient Population
    - Excluded/Low-Likelihood Population
    - Biomarker Strategy
    - Patient Match Score (0 - 100)
    - Confidence (0.0 - 1.0)
    Plus explicit evidence citations and mandatory regulatory disclaimer.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str

    # Output Populations
    best_patient_population: PopulationRecommendation
    secondary_patient_population: PopulationRecommendation
    excluded_patient_population: PopulationRecommendation

    # Biomarker Strategy
    biomarker_strategy: BiomarkerStrategy

    # Canonical Match Metrics
    patient_match_score: float = Field(ge=0.0, le=100.0, description="Population benefit concordance score")
    confidence: float = Field(ge=0.0, le=1.0, description="Evidence certainty score")
    mechanism: str = Field(description="Biochemical & cellular mechanism of action")

    # Regulatory Disclaimer
    disclaimer: str = Field(default=POPULATION_INTELLIGENCE_DISCLAIMER)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 4. Cohort Scenario Matching
# ==============================================================================

class PatientCohortQuery(BaseModel):
    """
    Patient cohort query to identify best matching drug assets.
    Example: 'ER+/HER2-mutant breast cancer after CDK4/6 progression'
    """
    disease_subtype: str = Field(default="HR+/HER2- Metastatic Breast Cancer")
    mutation: Optional[str] = Field(default="HER2 L755S / V777L")
    expression: Optional[str] = Field(default="ER-positive")
    amplification: Optional[str] = Field(default="HER2 non-amplified (IHC 1+/2+, FISH negative)")
    protein_expression: Optional[str] = Field(default="ER high (Allred 8)")
    biomarker: Optional[str] = Field(default="ER+/HER2-mutant")
    prior_therapy: List[str] = Field(default_factory=lambda: ["CDK4/6 inhibitor (e.g. palbociclib)", "Aromatase inhibitor"])
    resistance_state: Optional[str] = Field(default="Post-CDK4/6 progression")
    line_of_therapy: Optional[str] = Field(default="2L+ Metastatic")
    cns_status: Optional[str] = Field(default="Active or potential brain metastases")


class CandidateAssetMatchRank(BaseModel):
    asset_id: str
    asset_name: str
    match_score: float = Field(ge=0.0, le=100.0)
    rank: int
    population_fit: str
    mechanistic_synergy: str
    recommended_combination: Optional[str] = None
    evidence_citations: List[str] = Field(default_factory=list)


class PatientMatchScenarioResponse(BaseModel):
    query: PatientCohortQuery
    best_matched_asset: AssetPatientMatchProfile
    ranked_candidates: List[CandidateAssetMatchRank] = Field(default_factory=list)
    interpretation: str
    disclaimer: str = Field(default=POPULATION_INTELLIGENCE_DISCLAIMER)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 5. Legacy Compatibility Models (for /api/v1/decision/patient-match)
# ==============================================================================

class PatientProfileQuery(BaseModel):
    target: str = "HER2"
    indication: str = "Breast Cancer"
    setting: str = "Metastatic"
    mutations: List[str] = Field(
        default=["HER2 L755S", "HER2 V777L"],
        description="e.g. HER2 L755S, HER2 V777L, HER2 exon 20 insertion, HER2 amplification",
    )
    hormone_receptor_status: str = Field(
        default="ER-positive / HER2 non-amplified (IHC 1+)",
        description="e.g. ER-positive, ER-negative, HER2-amplified (IHC 3+)",
    )
    has_cns_metastases: bool = True
    prior_therapies: List[str] = Field(
        default=["CDK4/6 inhibitor (palbociclib)", "Letrozole", "Fulvestrant"]
    )


class PatientMatchItem(BaseModel):
    asset_id: str
    asset_name: str
    match_score: int = Field(ge=0, le=100)
    match_tier: str
    rationale: str
    recommended_combination: str
    resistance_risks_identified: List[str]
    cns_benefit_expected: bool


class PatientMatchResult(BaseModel):
    patient_query: PatientProfileQuery
    matches: List[PatientMatchItem]
    biomarker_interpretation: str
    calculation_lineage: str

