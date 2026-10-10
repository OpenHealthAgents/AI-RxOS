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
# 1. Enums: Evidence Levels, Species & Parameters
# ==============================================================================

class CNSEvidenceLevel(str, Enum):
    """
    Distinguishes the 5 evidentiary tiers of CNS data:
    1. direct measurement (e.g., in vivo microdialysis, surgical tissue LC-MS/MS, CSF sampling)
    2. animal evidence (e.g., rodent brain homogenates, orthotopic intracranial xenograft survival)
    3. in vitro inference (e.g., MDCK-MDR1 bidirectional transport, PAMPA-BBB, P-gp/BCRP efflux)
    4. mechanistic inference (e.g., physicochemical CNS-MPO score, logP, TPSA, MW)
    5. clinical CNS evidence (e.g., human trial prospective RANO-BM intracranial ORR, iPFS)
    """
    DIRECT_MEASUREMENT = "direct_measurement"
    ANIMAL_EVIDENCE = "animal_evidence"
    IN_VITRO_INFERENCE = "in_vitro_inference"
    MECHANISTIC_INFERENCE = "mechanistic_inference"
    CLINICAL_CNS_EVIDENCE = "clinical_cns_evidence"


class CNSSpecies(str, Enum):
    HUMAN = "human"
    MOUSE = "mouse"
    RAT = "rat"
    CYNOMOLGUS = "cynomolgus"
    IN_VITRO = "in_vitro"


class CNSParameterType(str, Enum):
    BRAIN_PLASMA_RATIO_KP = "brain_plasma_ratio_kp"
    KP_UU = "kp_uu"
    CSF_EXPOSURE = "csf_exposure"
    UNBOUND_BRAIN_CONCENTRATION = "unbound_brain_concentration"
    BBB_PENETRATION = "bbb_penetration"
    BRAIN_TUMOR_EXPOSURE = "brain_tumor_exposure"
    INTRACRANIAL_RESPONSE = "intracranial_response"
    CNS_PROGRESSION = "cns_progression"
    BRAIN_METASTASIS_RESPONSE = "brain_metastasis_response"


# ==============================================================================
# 2. Raw Observation Model
# ==============================================================================

class RawCNSObservation(BaseModel):
    """
    Empirical observation of a CNS property before score aggregation.
    Retains species, condition, raw text, normalized value, source citation, and evidence level.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    asset_id: str
    tenant_id: Optional[str] = None
    parameter_type: CNSParameterType
    evidence_level: CNSEvidenceLevel
    species: CNSSpecies
    experimental_condition: Optional[str] = Field(
        default=None,
        description="e.g. steady_state_oral, single_dose_iv, rano_bm_her2climb, mdck_mdr1_transwell",
    )
    raw_text_value: str
    normalized_value: float
    normalized_unit: Optional[str] = None
    source_citation: str
    source_url: Optional[str] = None
    pmid: Optional[str] = None
    nct_id: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    observation_date: Optional[date] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 3. Normalized Parameters & Formula Lineage
# ==============================================================================

class NormalizedCNSParameter(BaseModel):
    """Harmonized parameter normalized across species and assay conditions."""
    model_config = ConfigDict(from_attributes=True)

    parameter_type: CNSParameterType
    normalized_value: float
    normalized_unit: str
    evidence_level: CNSEvidenceLevel
    species: CNSSpecies
    raw_observation_ids: List[UUID] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    interpretation: str


class CNSScoreLineage(BaseModel):
    """Explicit mathematical formula lineage backing every CNS score."""
    model_config = ConfigDict(from_attributes=True)

    score_name: str
    formula: str
    inputs: Dict[str, Any]
    raw_observation_ids: List[UUID] = Field(default_factory=list)
    calculated_value: float
    evidence_level_contributions: Dict[str, float] = Field(default_factory=dict)
    evidence_gaps: List[str] = Field(default_factory=list)


# ==============================================================================
# 4. Canonical CNS Intelligence Profile
# ==============================================================================

class CNSIntelligenceProfile(BaseModel):
    """
    Canonical Profile containing the 3 required CNS scores:
    1. CNS Exposure Score (0 - 100)
    2. CNS Activity Score (0 - 100)
    3. CNS Translational Confidence (0.0 - 1.0)

    Strict Invariant:
    Never infer clinical CNS efficacy solely from physicochemical properties.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str

    # 3 Canonical Produced Scores
    cns_exposure_score: float = Field(ge=0.0, le=100.0, description="CNS penetration and tissue exposure score")
    cns_activity_score: float = Field(ge=0.0, le=100.0, description="Intracranial antitumor efficacy score")
    cns_translational_confidence: float = Field(ge=0.0, le=1.0, description="Translational concordance and evidence certainty")

    # Normalized Parameters across all 10 captured properties
    normalized_parameters: Dict[str, NormalizedCNSParameter] = Field(default_factory=dict)

    # Raw Underlying Evidence Observations
    raw_observations: List[RawCNSObservation] = Field(default_factory=list)

    # Formula Provenance Lineages
    lineages: Dict[str, CNSScoreLineage] = Field(default_factory=dict)

    # Evidence Level Distribution
    evidence_levels_present: List[CNSEvidenceLevel] = Field(default_factory=list)

    # Invariant Flag & Explicit Unknowns
    clinical_cns_efficacy_inferred_solely_from_physicochemical: bool = Field(
        default=False,
        description="Strictly False by design. Invariant: clinical efficacy cannot be inferred solely from physicochemical/in vitro metrics.",
    )
    unknowns: List[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 5. API Request & Response Schemas
# ==============================================================================

class EvaluateAssetCNSRequest(BaseModel):
    asset_id: str
    asset_name: Optional[str] = None
    custom_observations: Optional[List[RawCNSObservation]] = None


class EvaluateAssetCNSResponse(BaseModel):
    profile: CNSIntelligenceProfile


class CNSIntelligence(IntelligenceProfileBase):
    """Cutoff-aware CNS synthesis; measured exposure/activity never imply each other."""

    cns_exposure: IntelligenceValue
    predicted_cns_potential: IntelligenceValue
    cns_activity: IntelligenceValue
    predicted_cns_activity: IntelligenceValue
    brain_metastasis_relevance: IntelligenceValue
    confidence: IntelligenceValue
