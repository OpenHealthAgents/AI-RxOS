"""Canonical Domain Model for AI Drug Opportunity Discovery Engine.

Defines rich, validated Pydantic v2 domain models for all 43 core entities,
supporting entity resolution across developmental aliases, multi-target biology,
clinical trial outcomes, intellectual property, and auditable decision governance.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==============================================================================
# Enumerations
# ==============================================================================

class StrategicAction(StrEnum):
    PURSUE = "PURSUE"
    INVESTIGATE = "INVESTIGATE"
    PARTNER = "PARTNER"
    LICENSE = "LICENSE"
    MONITOR = "MONITOR"
    AVOID = "AVOID"


class DevelopmentStage(StrEnum):
    PRECLINICAL = "Preclinical"
    PHASE_I = "Phase I"
    PHASE_II = "Phase II"
    PHASE_III = "Phase III"
    APPROVED = "Approved"
    TERMINATED = "Terminated"


class ModalityCode(StrEnum):
    SMALL_MOLECULE = "SMALL_MOLECULE"
    ANTIBODY = "ANTIBODY"
    ADC = "ADC"
    PROTEIN = "PROTEIN"
    PEPTIDE = "PEPTIDE"
    CELL_THERAPY = "CELL_THERAPY"
    GENE_THERAPY = "GENE_THERAPY"
    RNA_THERAPY = "RNA_THERAPY"
    RADIOPHARMACEUTICAL = "RADIOPHARMACEUTICAL"
    VACCINE = "VACCINE"
    OTHER = "OTHER"


class EvidencePolarity(StrEnum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    NEUTRAL = "NEUTRAL"


class ScientificEvidenceState(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    AI_INFERENCE = "ai_inference"
    VERIFIED_FACT = "verified_fact"


class AliasType(StrEnum):
    GENERIC_NAME = "generic_name"
    BRAND_NAME = "brand_name"
    FORMER_NAME = "former_name"
    CHEMICAL_NAME = "chemical_name"
    LABORATORY_CODE = "laboratory_code"
    SYNONYM = "synonym"


class RegulatoryAuthority(StrEnum):
    FDA = "FDA"
    EMA = "EMA"
    PMDA = "PMDA"
    NMPA = "NMPA"
    MHRA = "MHRA"
    HEALTH_CANADA = "Health_Canada"


class RegulatoryEventType(StrEnum):
    IND_CLEARED = "IND_cleared"
    ORPHAN_DESIGNATION = "orphan_designation"
    FAST_TRACK = "fast_track"
    BREAKTHROUGH_THERAPY = "breakthrough_therapy"
    PRIORITY_REVIEW = "priority_review"
    NDA_BLA_ACCEPTED = "NDA_BLA_accepted"
    APPROVAL = "approval"
    COMPLETE_RESPONSE_LETTER = "complete_response_letter"
    CLINICAL_HOLD = "clinical_hold"


class AuditEventType(StrEnum):
    ASSET_CREATED = "ASSET_CREATED"
    ALIAS_ATTACHED = "ALIAS_ATTACHED"
    DEV_CODE_ATTACHED = "DEV_CODE_ATTACHED"
    ASSET_MERGED = "ASSET_MERGED"
    DECISION_RATIFIED = "DECISION_RATIFIED"
    DECISION_OVERRIDDEN = "DECISION_OVERRIDDEN"
    EVIDENCE_INGESTED = "EVIDENCE_INGESTED"
    SCORE_RECALCULATED = "SCORE_RECALCULATED"


# ==============================================================================
# Helper Normalizer
# ==============================================================================

def normalize_key(value: str) -> str:
    """Normalize text keys, code names, and synonyms for robust resolution."""
    cleaned = unicodedata.normalize("NFKC", value).strip().upper()
    return re.sub(r"[\s\-_]+", "", cleaned)


# ==============================================================================
# 1. Organization & User
# ==============================================================================

class Organization(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    slug: str
    tier: str = "enterprise"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    organization_id: Optional[UUID] = None
    email: str
    full_name: str
    role: str = "researcher"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 2. Company, Institution, Sponsor
# ==============================================================================

class Company(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    normalized_name: str = ""
    ticker: Optional[str] = None
    country: Optional[str] = None
    headquarters: Optional[str] = None
    company_type: str = "pharma"

    @field_validator("normalized_name", mode="before")
    @classmethod
    def set_normalized(cls, v: str, info: Any) -> str:
        if not v and "name" in info.data:
            return normalize_key(info.data["name"])
        return v or ""


class Institution(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    normalized_name: str = ""
    institution_type: str = "research_institute"
    city: Optional[str] = None
    country: Optional[str] = None

    @field_validator("normalized_name", mode="before")
    @classmethod
    def set_normalized(cls, v: str, info: Any) -> str:
        if not v and "name" in info.data:
            return normalize_key(info.data["name"])
        return v or ""


class Sponsor(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    company_id: Optional[UUID] = None
    institution_id: Optional[UUID] = None
    sponsor_type: str = "industry"


# ==============================================================================
# 3. Target, Gene, Protein
# ==============================================================================

class Gene(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    hgnc_symbol: str
    hgnc_id: Optional[str] = None
    entrez_id: Optional[str] = None
    ensembl_id: Optional[str] = None
    full_name: str
    chromosome: Optional[str] = None


class Protein(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    uniprot_id: str
    gene_id: Optional[UUID] = None
    protein_name: str
    sequence_length: Optional[int] = None
    molecular_weight: Optional[float] = None


class Target(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    symbol: str
    name: str
    gene_id: Optional[UUID] = None
    protein_id: Optional[UUID] = None
    target_class: str = "kinase"
    validation_level: str = "clinically_validated"


# ==============================================================================
# 4. Disease, Indication, CancerSubtype
# ==============================================================================

class Disease(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    mesh_id: Optional[str] = None
    icd10_code: Optional[str] = None
    doid: Optional[str] = None
    category: str = "oncology"


class Indication(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    disease_id: Optional[UUID] = None
    name: str
    setting: Optional[str] = "second_line"
    line_of_therapy: Optional[int] = 2
    prevalence_annual: Optional[int] = None


class CancerSubtype(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    disease_id: Optional[UUID] = None
    name: str
    receptor_status: Optional[str] = None
    histology: Optional[str] = None
    frequency_percentage: Optional[float] = None


# ==============================================================================
# 5. Biomarker & Mutation
# ==============================================================================

class Biomarker(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str
    target_id: Optional[UUID] = None
    biomarker_type: str = "mutation"
    diagnostic_test_available: bool = True


class Mutation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    biomarker_id: Optional[UUID] = None
    gene_id: Optional[UUID] = None
    protein_change: str
    exon: Optional[int] = None
    functional_consequence: str = "activating"


# ==============================================================================
# 6. Modality & MechanismOfAction
# ==============================================================================

class Modality(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    code: ModalityCode = ModalityCode.SMALL_MOLECULE
    name: str
    description: Optional[str] = None


class MechanismOfAction(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    target_id: Optional[UUID] = None
    name: str
    binding_type: str = "irreversible_covalent"
    selectivity_profile: Optional[str] = None


# ==============================================================================
# 7. Asset Identification, Development Codes, Aliases
# ==============================================================================

class AssetDevelopmentCode(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    code: str
    normalized_code: str = ""
    originator_company_id: Optional[UUID] = None
    is_primary: bool = False
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("normalized_code", mode="before")
    @classmethod
    def set_normalized(cls, v: str, info: Any) -> str:
        if not v and "code" in info.data:
            return normalize_key(info.data["code"])
        return v or ""


class AssetAlias(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    alias: str
    normalized_alias: str = ""
    alias_type: AliasType = AliasType.SYNONYM
    is_primary_for_type: bool = False
    verification_state: str = "verified"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("normalized_alias", mode="before")
    @classmethod
    def set_normalized(cls, v: str, info: Any) -> str:
        if not v and "alias" in info.data:
            return normalize_key(info.data["alias"])
        return v or ""


# ==============================================================================
# 8. Trial, Study, Publication
# ==============================================================================

class Trial(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    nct_id: str
    brief_title: str
    official_title: Optional[str] = None
    phase: str = "Phase 2"
    overall_status: str = "Active, not recruiting"
    sponsor_id: Optional[UUID] = None
    enrollment: Optional[int] = None
    primary_completion_date: Optional[date] = None
    results_first_posted: Optional[date] = None


class Study(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: Optional[UUID] = None
    name: str
    study_type: str = "interventional_trial"
    lead_institution_id: Optional[UUID] = None


class Publication(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    pmid: Optional[str] = None
    doi: Optional[str] = None
    pmcid: Optional[str] = None
    title: str
    journal: Optional[str] = None
    publication_year: int
    published_date: Optional[date] = None
    url: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    abstract: Optional[str] = None


# ==============================================================================
# 9. Evidence & EvidenceObservation
# ==============================================================================

class Evidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    publication_id: Optional[UUID] = None
    trial_id: Optional[UUID] = None
    evidence_type: str = "literature"
    source_ref: str
    citation: str
    publication_year: int
    as_of_date: date
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    is_verified: bool = True
    excerpt: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    evidence_id: UUID
    asset_id: UUID
    parameter_name: str
    observed_value: str
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    statistical_significance: Optional[str] = None
    observation_state: ScientificEvidenceState = ScientificEvidenceState.VERIFIED_FACT


# ==============================================================================
# 10. ClinicalOutcome & PreclinicalResult
# ==============================================================================

class ClinicalOutcome(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    trial_id: UUID
    asset_id: UUID
    endpoint_name: str
    endpoint_type: str = "primary"
    cohort_description: Optional[str] = None
    response_rate: Optional[float] = None
    median_months: Optional[float] = None
    hazard_ratio: Optional[float] = None
    confidence_interval: Optional[str] = None
    is_statistically_significant: Optional[bool] = None


class PreclinicalResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    assay_type: str = "biochemical_kinase"
    target_id: Optional[UUID] = None
    cell_line: Optional[str] = None
    ic50_nm: Optional[float] = None
    ec50_nm: Optional[float] = None
    tumor_growth_inhibition_pct: Optional[float] = None
    is_wt_sparing: Optional[bool] = None


# ==============================================================================
# 11. SafetyObservation & CNSObservation
# ==============================================================================

class SafetyObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    adverse_event_name: str
    grade_all_rate: Optional[float] = None
    grade_3_plus_rate: Optional[float] = None
    dose_limiting_toxicity: bool = False
    discontinuation_rate: Optional[float] = None
    therapeutic_index_rating: Optional[str] = "favorable"


class CNSObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    brain_to_plasma_ratio: Optional[float] = None
    csf_penetration_verified: bool = False
    intracranial_orr: Optional[float] = None
    intracranial_pfs_months: Optional[float] = None
    leptomeningeal_activity: bool = False
    cns_score: int = Field(default=50, ge=0, le=100)


# ==============================================================================
# 12. PatientPopulation, ResistanceMechanism, Combination
# ==============================================================================

class PatientPopulation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    population_name: str
    indication_id: Optional[UUID] = None
    biomarker_id: Optional[UUID] = None
    prior_lines: Optional[str] = None
    cns_metastases_benefit: bool = True
    match_score: float = Field(default=80.0, ge=0.0, le=100.0)


class ResistanceMechanism(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    name: str
    impact_level: str = "High"
    is_predicted: bool = False
    mechanism_description: str


class Combination(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    primary_asset_id: UUID
    partner_name: str
    partner_asset_id: Optional[UUID] = None
    synergy_type: str
    rationale: str
    clinical_status: str


# ==============================================================================
# 13. Patent, LicenseEvent, Partnership, RegulatoryEvent
# ==============================================================================

class Patent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    patent_number: str
    title: str
    assignee_company_id: Optional[UUID] = None
    priority_date: Optional[date] = None
    filing_date: Optional[date] = None
    grant_date: Optional[date] = None
    expiration_date: Optional[date] = None
    status: str = "granted"


class LicenseEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    licensor_company_id: UUID
    licensee_company_id: UUID
    event_type: str = "exclusive_license"
    territory: str = "Global"
    effective_date: date
    disclosed_upfront_usd: Optional[int] = None
    disclosed_milestones_usd: Optional[int] = None


class Partnership(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    partner_company_id: UUID
    scope: str
    start_date: date
    status: str = "active"


class RegulatoryEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    authority: RegulatoryAuthority = RegulatoryAuthority.FDA
    event_type: RegulatoryEventType = RegulatoryEventType.FAST_TRACK
    indication_id: Optional[UUID] = None
    event_date: date
    dossier_notes: Optional[str] = None


# ==============================================================================
# 14. CommercialObservation & CompetitiveAsset
# ==============================================================================

class CommercialObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    estimated_peak_sales_usd: Optional[int] = None
    addressable_market_usd: Optional[int] = None
    target_patient_annual_count: Optional[int] = None
    pricing_strategy: Optional[str] = None
    market_exclusivity_expiry: Optional[date] = None


class CompetitiveAsset(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    target_asset_id: UUID
    competitor_asset_id: UUID
    competitive_relationship: str = "direct_benchmark"
    differentiating_advantage: str


# ==============================================================================
# 15. Decision, Recommendation, Score, ScoreComponent, Prediction
# ==============================================================================

class Decision(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    organization_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    action: StrategicAction = StrategicAction.PURSUE
    is_human_override: bool = False
    ai_suggested_action: StrategicAction = StrategicAction.PURSUE
    clinical_justification: str
    decision_timestamp: datetime = Field(default_factory=datetime.utcnow)
    checklist: Dict[str, bool] = Field(default_factory=dict)


class Recommendation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    action: StrategicAction = StrategicAction.PURSUE
    confidence: float = Field(ge=0.0, le=100.0)
    rationale: str
    badge_text: str
    model_version: str = "Model v0.1"


class ScoreComponent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    score_id: UUID
    component_name: str
    weight: float
    raw_value: float
    weighted_value: float


class Score(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    score_type: str = "development_potential"
    numeric_score: float = Field(ge=0.0, le=100.0)
    confidence_interval_low: Optional[float] = None
    confidence_interval_high: Optional[float] = None
    model_lineage: str = "Calibrated Multi-Attribute Engine"
    components: List[ScoreComponent] = Field(default_factory=list)


class Prediction(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    transition_stage: str
    predicted_probability: float = Field(ge=0.0, le=1.0)
    model_version: str = "Model v0.1"
    calibration_data: Optional[str] = None


# ==============================================================================
# 16. BacktestSnapshot & AuditEvent
# ==============================================================================

class BacktestSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    cutoff_date: date
    predicted_action: StrategicAction
    predicted_dps: float
    eligible_evidence_count: int
    suppressed_future_evidence_count: int
    ground_truth_outcome: str
    prediction_accuracy: str
    anti_leakage_audit_passed: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    event_type: AuditEventType
    entity_id: UUID
    entity_type: str
    actor_id: Optional[UUID] = None
    actor_name: str
    summary: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 17. Core Asset Aggregate
# ==============================================================================

class Asset(BaseModel):
    """Core Asset aggregate maintaining complete multi-dimensional lifecycle data."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    preferred_name: str
    canonical_slug: str = ""
    modality_id: Optional[UUID] = None
    modality_code: ModalityCode = ModalityCode.SMALL_MOLECULE
    primary_target_id: Optional[UUID] = None
    primary_target_symbol: str = "HER2"
    primary_moa_id: Optional[UUID] = None
    primary_moa_name: Optional[str] = None

    owner_company_id: Optional[UUID] = None
    owner_company_name: str = "Boehringer Ingelheim"
    developer_company_id: Optional[UUID] = None
    developer_company_name: Optional[str] = None
    sponsor_id: Optional[UUID] = None

    current_development_stage: DevelopmentStage = DevelopmentStage.PHASE_II
    status_label: str = "Investigational"
    primary_indication_id: Optional[UUID] = None
    primary_indication_name: str = "HER2-mutant metastatic breast cancer"

    is_deprecated: bool = False
    merged_into_asset_id: Optional[UUID] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relational sub-collections supported directly on Asset aggregate
    development_codes: List[AssetDevelopmentCode] = Field(default_factory=list)
    aliases: List[AssetAlias] = Field(default_factory=list)
    targets: List[Target] = Field(default_factory=list)
    indications: List[Indication] = Field(default_factory=list)
    trials: List[Trial] = Field(default_factory=list)
    publications: List[Publication] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    outcomes: List[ClinicalOutcome] = Field(default_factory=list)
    patents: List[Patent] = Field(default_factory=list)
    partnerships: List[Partnership] = Field(default_factory=list)
    regulatory_events: List[RegulatoryEvent] = Field(default_factory=list)

    @field_validator("canonical_slug", mode="before")
    @classmethod
    def set_canonical_slug(cls, v: str, info: Any) -> str:
        if not v and "preferred_name" in info.data:
            return re.sub(r"[^a-z0-9]+", "-", info.data["preferred_name"].lower()).strip("-")
        return v or ""

    def get_all_identifiers(self) -> List[str]:
        """Returns all recognized names, codes, and aliases normalized for resolution."""
        identifiers = [normalize_key(self.preferred_name)]
        for dev in self.development_codes:
            identifiers.append(normalize_key(dev.code))
        for alias in self.aliases:
            identifiers.append(normalize_key(alias.alias))
        return list(set(identifiers))

    def has_code_or_alias(self, query: str) -> bool:
        """Check if asset matches a given raw string query under normalization."""
        norm_q = normalize_key(query)
        return norm_q in self.get_all_identifiers()
