from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 1. Enums
# ==============================================================================

class CompetitiveDensityTier(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class DifferentiationTier(str, Enum):
    HIGHLY_DIFFERENTIATED = "HIGHLY_DIFFERENTIATED"
    MODERATELY_DIFFERENTIATED = "MODERATELY_DIFFERENTIATED"
    MINIMALLY_DIFFERENTIATED = "MINIMALLY_DIFFERENTIATED"
    UNDIFFERENTIATED = "UNDIFFERENTIATED"


class CompetitiveRiskTier(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComparisonAdvantagePolarity(str, Enum):
    FAVORABLE = "FAVORABLE"      # Focal asset holds clear advantage
    PARITY = "PARITY"            # Roughly equivalent / neutral
    UNFAVORABLE = "UNFAVORABLE"  # Competitor holds advantage


# ==============================================================================
# 2. Competitor Summary & Cohort Breakdown
# ==============================================================================

class CompetitorSummary(BaseModel):
    """
    Structured summary of a competitor entity.
    """
    model_config = ConfigDict(from_attributes=True)

    competitor_id: str
    name: str
    sponsor_or_owner: str
    stage: str
    modality: str
    target: str
    mechanism: str
    is_approved_soc: bool = False
    is_clinical_stage: bool = False
    is_emerging_academic: bool = False
    primary_indication: str
    biomarkers: List[str] = Field(default_factory=list)
    patient_populations: List[str] = Field(default_factory=list)
    shared_attributes: List[str] = Field(default_factory=list)
    brief_profile: str


class CompetitorCohortBreakdown(BaseModel):
    """
    Categorizes the competitive landscape for an asset across required cohorts:
    - direct competitors
    - same target
    - same mechanism
    - same biomarker
    - same indication
    - same patient population
    - same modality
    - clinical-stage competitors
    - approved standards of care
    - emerging academic programs
    """
    model_config = ConfigDict(from_attributes=True)

    direct_competitors: List[CompetitorSummary] = Field(default_factory=list)
    same_target: List[CompetitorSummary] = Field(default_factory=list)
    same_mechanism: List[CompetitorSummary] = Field(default_factory=list)
    same_biomarker: List[CompetitorSummary] = Field(default_factory=list)
    same_indication: List[CompetitorSummary] = Field(default_factory=list)
    same_patient_population: List[CompetitorSummary] = Field(default_factory=list)
    same_modality: List[CompetitorSummary] = Field(default_factory=list)
    clinical_stage_competitors: List[CompetitorSummary] = Field(default_factory=list)
    approved_standards_of_care: List[CompetitorSummary] = Field(default_factory=list)
    emerging_academic_programs: List[CompetitorSummary] = Field(default_factory=list)


# ==============================================================================
# 3. Eleven Head-to-Head Comparison Dimensions
# ==============================================================================

class DimensionComparison(BaseModel):
    """
    Single dimension head-to-head comparison between focal asset and competitor.
    """
    model_config = ConfigDict(from_attributes=True)

    dimension_name: str
    focal_value: str
    competitor_value: str
    polarity: ComparisonAdvantagePolarity
    advantage_delta_score: float = Field(
        ge=-10.0, le=10.0,
        description="Scored relative delta: >0 favorable, 0 parity, <0 unfavorable"
    )
    rationale: str


class HeadToHeadComparison(BaseModel):
    """
    Full head-to-head evaluation across all 11 required dimensions:
    potency, selectivity, CNS, clinical stage, efficacy, safety,
    biomarker, resistance, combination, ownership, commercial opportunity.
    """
    model_config = ConfigDict(from_attributes=True)

    competitor_id: str
    competitor_name: str
    competitor_stage: str
    is_approved_soc: bool
    overall_advantage: ComparisonAdvantagePolarity
    composite_advantage_score: float = Field(
        ge=-100.0, le=100.0,
        description="Weighted composite advantage score over this competitor"
    )

    # 11 Comparison Dimensions
    potency: DimensionComparison
    selectivity: DimensionComparison
    cns: DimensionComparison
    clinical_stage: DimensionComparison
    efficacy: DimensionComparison
    safety: DimensionComparison
    biomarker: DimensionComparison
    resistance: DimensionComparison
    combination: DimensionComparison
    ownership: DimensionComparison
    commercial_opportunity: DimensionComparison

    key_differentiators: List[str] = Field(default_factory=list)
    competitive_threat_level: str
    summary: str


# ==============================================================================
# 4. Four Core Output Evaluations
# ==============================================================================

class CompetitiveDensityEvaluation(BaseModel):
    """
    Quantifies market and clinical crowding around target, indication, and population.
    """
    model_config = ConfigDict(from_attributes=True)

    density_score: float = Field(ge=0.0, le=100.0)
    density_tier: CompetitiveDensityTier
    total_competitors_count: int
    direct_competitors_count: int
    clinical_competitors_count: int
    approved_soc_count: int
    academic_programs_count: int
    stage_distribution: Dict[str, int] = Field(default_factory=dict)
    modality_distribution: Dict[str, int] = Field(default_factory=dict)
    crowding_assessment: str
    density_formula: str = (
        "DensityScore = min(100.0, DirectCompetitors*20.0 + ClinicalCompetitors*10.0 + "
        "ApprovedSOC*15.0 + AcademicPrograms*5.0)"
    )


class DifferentiationEvaluation(BaseModel):
    """
    Evaluates clinical, mechanistic, safety, and PK differentiation relative to peers and SOC.
    """
    model_config = ConfigDict(from_attributes=True)

    differentiation_score: float = Field(ge=0.0, le=100.0)
    differentiation_tier: DifferentiationTier
    key_usps: List[str] = Field(
        default_factory=list,
        description="Unique Selling Propositions that set the asset apart"
    )
    clinical_moat: str
    vulnerabilities: List[str] = Field(default_factory=list)
    differentiation_formula: str = (
        "DiffScore = 0.15*SelectivityAdv + 0.15*CNSAdv + 0.15*SafetyAdv + 0.15*EfficacyAdv + "
        "0.10*PotencyAdv + 0.10*StageMaturity + 0.05*BiomarkerAdv + 0.05*ResistanceAdv + "
        "0.05*CombinationAdv + 0.05*OwnershipAdv"
    )


class CompetitiveRiskEvaluation(BaseModel):
    """
    Assesses commercial and clinical displacement risk from SOC dominance and fast-followers.
    """
    model_config = ConfigDict(from_attributes=True)

    risk_score: float = Field(ge=0.0, le=100.0)
    risk_tier: CompetitiveRiskTier
    primary_threats: List[str] = Field(default_factory=list)
    soc_displacement_barrier: str
    displacement_scenarios: List[str] = Field(default_factory=list)
    mitigation_strategies: List[str] = Field(default_factory=list)
    risk_formula: str = (
        "RiskScore = 0.30*SOCDominance + 0.25*CrowdingDensity + "
        "0.30*(100 - DifferentiationScore) + 0.15*FastFollowerLeapfrog"
    )


class WhiteSpaceOpportunityRecord(BaseModel):
    """
    Identifies unaddressed niches, underserved populations, or mechanistic gaps
    with limited or zero direct competition.
    """
    model_config = ConfigDict(from_attributes=True)

    opportunity_id: str
    niche_name: str
    target_patient_population: str
    unmet_clinical_need: str
    mechanistic_or_clinical_gap: str
    competitive_intensity: str
    commercial_attractiveness: str
    recommended_development_action: str


# ==============================================================================
# 5. Top-Level Aggregate Domain Profile
# ==============================================================================

class CompetitiveIntelligenceProfile(BaseModel):
    """
    Comprehensive Competitive Intelligence Profile for a therapeutic asset.
    Contains competitor identification across all required cohorts,
    11 head-to-head comparison dimensions against key peers and SOC,
    and the 4 core deliverables: Competitive Density, Differentiation Score,
    Competitive Risk, and White-Space Opportunities.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    asset_id: str
    asset_name: str
    target: str
    primary_indication: str
    patient_population: str
    modality: str
    stage: str
    cohorts: CompetitorCohortBreakdown
    head_to_head_comparisons: List[HeadToHeadComparison] = Field(default_factory=list)
    competitive_density: CompetitiveDensityEvaluation
    differentiation: DifferentiationEvaluation
    competitive_risk: CompetitiveRiskEvaluation
    white_space_opportunities: List[WhiteSpaceOpportunityRecord] = Field(default_factory=list)
    evidence_citations: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvaluateCompetitiveRequest(BaseModel):
    """
    Request payload to evaluate an asset's competitive landscape dynamically.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: Optional[str] = None
    target: str = "HER2"
    indication: str = "Non-Small Cell Lung Cancer"
    patient_population: str = "Pretreated HER2-mutant oncology"
    modality: str = "Small Molecule TKI"
    stage: str = "Phase II"
