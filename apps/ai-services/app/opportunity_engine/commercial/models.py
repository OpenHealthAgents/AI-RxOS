from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

COMMERCIAL_INTELLIGENCE_DISCLAIMER = (
    "Do not fabricate market size. IP, clinical, and pricing intelligence does not "
    "constitute forward revenue guarantees. Projections reflect explicit mathematical "
    "derivations with declared assumption provenance (Observed, Externally sourced, "
    "Modeled, Assumed, or Unknown)."
)


# ==============================================================================
# 1. Assumption Provenance & Tiers Enums
# ==============================================================================

class AssumptionProvenance(str, Enum):
    OBSERVED = "Observed"                    # Verified clinical trial result or empirical label
    EXTERNALLY_SOURCED = "Externally sourced"  # Published registry, SEER/Globocan, SEC filing, NCCN
    MODELED = "Modeled"                      # Mathematically derived from structured inputs
    ASSUMED = "Assumed"                      # Analytical hypothesis or expert consensus proxy
    UNKNOWN = "Unknown"                      # Uncharacterized parameter, penalizes confidence


class MarketAttractivenessTier(str, Enum):
    VERY_HIGH = "VERY_HIGH"  # Multi-billion blockbuster headroom ($2B+)
    HIGH = "HIGH"            # Major market ($1B - $2B)
    MODERATE = "MODERATE"    # Mid-sized market ($500M - $1B)
    LOW = "LOW"              # Limited commercial ceiling (<$500M)
    NICHE = "NICHE"          # Ultra-orphan or highly restricted segment


class CompetitivePressureTier(str, Enum):
    INTENSE = "INTENSE"      # Multiple approved blockbusters and crowded Phase 3 pipeline
    HIGH = "HIGH"            # Established standard of care with emerging direct fast-followers
    MODERATE = "MODERATE"    # 1-2 standard of care options with manageable pipeline entrants
    LOW = "LOW"              # Minimal competition, greenfield or underserved segment


class CommercialUnmetNeedTier(str, Enum):
    CRITICAL = "CRITICAL"    # Lethal refractory setting with zero effective alternatives
    HIGH = "HIGH"            # Standard therapies exhibit severe toxicity or short durability
    MODERATE = "MODERATE"    # Incremental benefit over existing acceptable regimens
    LOW = "LOW"              # Disease well controlled by existing generic or approved agents


# ==============================================================================
# 2. Assumption Provenance Audit Record
# ==============================================================================

class CommercialAssumptionRecord(BaseModel):
    """
    Every commercial assumption must explicitly identify its epistemic provenance:
    Observed, Externally sourced, Modeled, Assumed, or Unknown.
    """
    model_config = ConfigDict(from_attributes=True)

    key: str
    parameter_label: str
    parameter_value: str
    provenance: AssumptionProvenance
    source_citation: str
    methodology: str
    confidence: float = Field(ge=0.0, le=1.0)


# ==============================================================================
# 3. Eleven Evaluation Dimensions Sub-Models
# ==============================================================================

class AddressablePopulationEvaluation(BaseModel):
    """
    Dimension 1: Addressable population across major geographic markets.
    """
    model_config = ConfigDict(from_attributes=True)

    annual_incidence_us: int
    annual_incidence_eu5: int
    annual_incidence_jp: int
    metastatic_advanced_rate_pct: float = Field(ge=0.0, le=100.0)
    total_metastatic_pool: int
    provenance: AssumptionProvenance
    source_citation: str
    methodology: str


class BiomarkerDefinedPopulationEvaluation(BaseModel):
    """
    Dimension 2: Biomarker prevalence, diagnostic testing adoption, and targeted niche size.
    """
    model_config = ConfigDict(from_attributes=True)

    biomarker_name: str
    biomarker_prevalence_pct: float = Field(ge=0.0, le=100.0)
    testing_penetration_rate_pct: float = Field(ge=0.0, le=100.0)
    target_eligible_patient_pool: int
    provenance: AssumptionProvenance
    source_citation: str
    calculation_formula: str = (
        "EligiblePatients = TotalMetastaticPool * (BiomarkerPrevalencePct / 100) * "
        "(TestingPenetrationPct / 100)"
    )


class TreatmentDurationEvaluation(BaseModel):
    """
    Dimension 3: Treatment duration, progression-free survival, and persistence.
    """
    model_config = ConfigDict(from_attributes=True)

    median_pfs_months: float
    median_duration_of_treatment_months: float
    treatment_cycles_annual_equivalent: float
    compliance_persistence_rate_pct: float = Field(ge=0.0, le=100.0)
    provenance: AssumptionProvenance
    source_citation: str


class StandardOfCareEvaluation(BaseModel):
    """
    Dimension 4: Incumbent standard of care regimens, benchmarks, and limitations.
    """
    model_config = ConfigDict(from_attributes=True)

    soc_regimen_name: str
    soc_efficacy_benchmark: str
    soc_shortcomings: List[str] = Field(default_factory=list)
    soc_market_share_pct: float = Field(ge=0.0, le=100.0)
    provenance: AssumptionProvenance
    source_citation: str


class UnmetNeedEvaluation(BaseModel):
    """
    Dimension 5: Disease lethality, lack of alternatives, and urgency of innovation.
    """
    model_config = ConfigDict(from_attributes=True)

    unmet_need_score: float = Field(ge=0.0, le=100.0)
    unmet_need_tier: CommercialUnmetNeedTier
    drivers: List[str] = Field(default_factory=list)
    post_progression_prognosis: str
    provenance: AssumptionProvenance
    source_citation: str


class CommercialCompetitiveDensityEvaluation(BaseModel):
    """
    Dimension 6: Market crowding, commercial alternatives, and class saturation.
    """
    model_config = ConfigDict(from_attributes=True)

    density_score: float = Field(ge=0.0, le=100.0)
    active_commercial_competitors_count: int
    pipeline_competitors_count: int
    crowding_summary: str
    provenance: AssumptionProvenance


class ClinicalDifferentiationEvaluation(BaseModel):
    """
    Dimension 7: Therapeutic differentiation over SOC in efficacy, safety, and PK.
    """
    model_config = ConfigDict(from_attributes=True)

    differentiation_score: float = Field(ge=0.0, le=100.0)
    key_differentiators: List[str] = Field(default_factory=list)
    commercial_moat: str
    provenance: AssumptionProvenance


class PotentialLineOfTherapyEvaluation(BaseModel):
    """
    Dimension 8: Recommended regulatory entry point and sequence in care pathways.
    """
    model_config = ConfigDict(from_attributes=True)

    initial_target_line: str
    potential_expansion_line: str
    nccn_guideline_positioning_goal: str
    rationale: str
    provenance: AssumptionProvenance


class PricingAnalogsEvaluation(BaseModel):
    """
    Dimension 9: Oncology pricing benchmarks, WAC, and gross-to-net realized revenue.
    """
    model_config = ConfigDict(from_attributes=True)

    benchmark_drug_name: str
    benchmark_modality: str
    monthly_wac_usd: float = Field(ge=0.0)
    annual_gross_treatment_cost_usd: float = Field(ge=0.0)
    gross_to_net_discount_pct: float = Field(ge=0.0, le=100.0)
    net_realized_monthly_usd: float = Field(ge=0.0)
    provenance: AssumptionProvenance
    pricing_source: str


class PipelineCrowdingEvaluation(BaseModel):
    """
    Dimension 10: Phase 3 competitive threats, fast-followers, and entry timing.
    """
    model_config = ConfigDict(from_attributes=True)

    phase_3_threats_count: int
    fast_followers_count: int
    threat_assessment: str
    leapfrog_risk: str
    provenance: AssumptionProvenance


class MarketExpansionScenario(BaseModel):
    """
    Dimension 11: Specific line-of-therapy, combination, or multi-tumor expansion scenarios.
    """
    model_config = ConfigDict(from_attributes=True)

    scenario_name: str
    target_indication: str
    target_line: str
    incremental_patient_pool: int
    timeline_years: float
    regulatory_pathway: str
    peak_penetration_potential_pct: float = Field(ge=0.0, le=100.0)
    estimated_incremental_revenue_usd: float = Field(ge=0.0)
    provenance: AssumptionProvenance


# ==============================================================================
# 4. Financial & Market Revenue Projections Model
# ==============================================================================

class ModeledRevenueProjections(BaseModel):
    """
    Explicitly modeled annual revenues under base, bull, and bear scenarios.
    All figures derived deterministically:
    Revenue = EligiblePatients * PeakPenetrationPct * TreatmentMonths * MonthlyNetPrice.
    """
    model_config = ConfigDict(from_attributes=True)

    base_peak_share_pct: float = Field(ge=0.0, le=100.0)
    base_peak_sales_usd: float = Field(ge=0.0)
    bull_peak_share_pct: float = Field(ge=0.0, le=100.0)
    bull_peak_sales_usd: float = Field(ge=0.0)
    bear_peak_share_pct: float = Field(ge=0.0, le=100.0)
    bear_peak_sales_usd: float = Field(ge=0.0)
    projected_peak_year: int
    derivation_lineage: str = (
        "PeakSales = TargetEligiblePatients * (PeakSharePct / 100) * "
        "(TreatmentDurationMonths / 12) * AnnualNetRealizedPrice"
    )


# ==============================================================================
# 5. Top-Level Aggregate Domain Profile
# ==============================================================================

class CommercialOpportunityProfile(BaseModel):
    """
    Comprehensive Commercial Opportunity Profile for a biopharmaceutical asset.
    Evaluates 11 dimensions and produces:
    - Commercial Opportunity Score (0 - 100)
    - Market Attractiveness
    - Competitive Pressure
    - Unmet Need
    - Commercial Confidence (0.0 - 1.0)
    Strictly preserves provenance across all assumptions.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    asset_id: str
    asset_name: str
    indication: str
    target: str
    potential_line_of_therapy: str

    # Core Produced Outputs
    commercial_opportunity_score: float = Field(ge=0.0, le=100.0)
    market_attractiveness_score: float = Field(ge=0.0, le=100.0)
    market_attractiveness_tier: MarketAttractivenessTier
    competitive_pressure_score: float = Field(ge=0.0, le=100.0)
    competitive_pressure_tier: CompetitivePressureTier
    unmet_need_score: float = Field(ge=0.0, le=100.0)
    unmet_need_tier: CommercialUnmetNeedTier
    commercial_confidence: float = Field(ge=0.0, le=1.0)

    # Eleven Evaluated Dimensions
    addressable_population: AddressablePopulationEvaluation
    biomarker_defined_population: BiomarkerDefinedPopulationEvaluation
    treatment_duration: TreatmentDurationEvaluation
    standard_of_care: StandardOfCareEvaluation
    unmet_need: UnmetNeedEvaluation
    competitive_density: CommercialCompetitiveDensityEvaluation
    clinical_differentiation: ClinicalDifferentiationEvaluation
    potential_line_of_therapy_eval: PotentialLineOfTherapyEvaluation
    pricing_analogs: PricingAnalogsEvaluation
    pipeline_crowding: PipelineCrowdingEvaluation
    market_expansion_opportunities: List[MarketExpansionScenario] = Field(default_factory=list)

    # Modeled Projections & Epistemic Audit
    modeled_revenue_projections: ModeledRevenueProjections
    assumptions_audit: List[CommercialAssumptionRecord] = Field(default_factory=list)
    has_unknown_assumptions: bool = False
    disclaimer: str = Field(default=COMMERCIAL_INTELLIGENCE_DISCLAIMER)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_commercial_confidence_and_provenance(self) -> CommercialOpportunityProfile:
        """
        Enforce epistemic invariant:
        If key commercial assumptions are UNKNOWN, confidence cannot exceed 0.40.
        """
        unknown_assumptions = [
            a for a in self.assumptions_audit if a.provenance == AssumptionProvenance.UNKNOWN
        ]
        if unknown_assumptions or self.has_unknown_assumptions:
            self.has_unknown_assumptions = True
            if self.commercial_confidence > 0.40:
                raise ValueError(
                    f"Commercial confidence ({self.commercial_confidence}) cannot exceed 0.40 "
                    f"when key assumptions are UNKNOWN: {[a.key for a in unknown_assumptions]}."
                )
        return self


class EvaluateCommercialRequest(BaseModel):
    """
    Request payload to evaluate an asset's commercial opportunity.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: Optional[str] = None
    target: str = "HER2"
    indication: str = "Non-Small Cell Lung Cancer"
    potential_line_of_therapy: str = "2L+ post-platinum / post-ADC"
