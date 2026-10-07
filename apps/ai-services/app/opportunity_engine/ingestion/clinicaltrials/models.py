from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class NormalizedClinicalStage(str, Enum):
    PRECLINICAL = "Preclinical"
    IND_ENABLING = "IND-enabling"
    PHASE_I = "Phase I"
    PHASE_IB = "Phase Ib"
    PHASE_II = "Phase II"
    PHASE_II_III = "Phase II/III"
    PHASE_III = "Phase III"
    REGULATORY_REVIEW = "Regulatory review"
    APPROVED = "Approved"
    WITHDRAWN = "Withdrawn"
    TERMINATED = "Terminated"
    DISCONTINUED = "Discontinued"


# ==============================================================================
# 1. Structural Trial Elements
# ==============================================================================

class InterventionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    intervention_type: str = "DRUG"
    name: str
    description: Optional[str] = None


class ArmItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    arm_label: str
    arm_type: str = "EXPERIMENTAL"
    intervention_names: List[str] = Field(default_factory=list)


class EndpointItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    endpoint_title: str
    endpoint_type: str = "PRIMARY"
    time_frame: Optional[str] = None
    description: Optional[str] = None


class TrialOutcomeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    endpoint_name: str
    metric: str  # ORR, mPFS, mOS, DCR
    value: Optional[float] = None
    unit: Optional[str] = None
    confidence_interval: Optional[str] = None


class AdverseEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    term: str
    grade: Optional[str] = "Grade 3+"
    affected_count: Optional[int] = None
    total_evaluated: Optional[int] = None
    frequency_pct: Optional[float] = None
    is_serious: bool = False


# ==============================================================================
# 2. Status History Tracking Over Time
# ==============================================================================

class TrialStatusHistory(BaseModel):
    """
    Captures temporal milestone transition points in the trial lifecycle.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    nct_id: str
    as_of_date: date
    overall_status: str
    normalized_stage: NormalizedClinicalStage
    why_stopped: Optional[str] = None
    enrollment: Optional[int] = None
    results_posted: bool = False
    change_summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 3. Comprehensive Clinical Trial Record
# ==============================================================================

class ClinicalTrialRecord(BaseModel):
    """
    Comprehensive ClinicalTrials.gov record capturing all 20 required attributes:
    NCT ID, study title, sponsor, collaborators, phase, status, enrollment,
    intervention, arm, condition, biomarker, population, eligibility, endpoint,
    outcome, results, adverse events, termination, withdrawal, publication links.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    nct_id: str
    study_title: str
    official_title: Optional[str] = None
    sponsor: str
    collaborators: List[str] = Field(default_factory=list)
    phase_raw: str
    normalized_stage: NormalizedClinicalStage = NormalizedClinicalStage.PHASE_I
    status: str
    enrollment: Optional[int] = None
    interventions: List[InterventionItem] = Field(default_factory=list)
    arms: List[ArmItem] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    biomarkers: List[str] = Field(default_factory=list)
    population: str = ""
    eligibility: Dict[str, Any] = Field(default_factory=dict)
    endpoints: List[EndpointItem] = Field(default_factory=list)
    outcomes: List[TrialOutcomeItem] = Field(default_factory=list)
    results: Optional[Dict[str, Any]] = None
    adverse_events: List[AdverseEventItem] = Field(default_factory=list)
    termination_reason: Optional[str] = None
    termination: Optional[str] = None
    why_stopped: Optional[str] = None
    withdrawal_reason: Optional[str] = None
    publication_links: List[str] = Field(default_factory=list)
    start_date: Optional[date] = None
    primary_completion_date: Optional[date] = None
    results_first_posted_date: Optional[date] = None
    status_history: List[TrialStatusHistory] = Field(default_factory=list)
    content_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_content_hash(self) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.nct_id.strip().upper().encode("utf-8"))
        hasher.update(self.status.strip().upper().encode("utf-8"))
        hasher.update(str(self.enrollment or 0).encode("utf-8"))
        stage_str = self.normalized_stage.value if hasattr(self.normalized_stage, "value") else str(self.normalized_stage)
        hasher.update(stage_str.encode("utf-8"))
        return hasher.hexdigest()

    def model_post_init(self, __context: Any) -> None:
        if not self.termination_reason:
            if self.termination:
                self.termination_reason = self.termination
            elif self.why_stopped:
                self.termination_reason = self.why_stopped
        if not self.termination and self.termination_reason:
            self.termination = self.termination_reason
        if not self.why_stopped and self.termination_reason:
            self.why_stopped = self.termination_reason
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()


# ==============================================================================
# 4. Resolution Mappings
# ==============================================================================

class TrialAssetMapping(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    nct_id: str
    asset_id: UUID
    canonical_name: str
    intervention_name: str
    is_primary: bool = True
    confidence: float = 1.0


class TrialIndicationMapping(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    nct_id: str
    indication_id: Optional[UUID] = None
    condition_name: str
    cancer_subtype: Optional[str] = None
    confidence: float = 0.95


class TrialBiomarkerMapping(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    nct_id: str
    biomarker_id: Optional[UUID] = None
    biomarker_text: str
    gene_symbol: Optional[str] = None
    inclusion_status: str = "REQUIRED"


class TrialCompanyMapping(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    nct_id: str
    company_id: Optional[UUID] = None
    company_name: str
    role: str = "LEAD_SPONSOR"


class TrialResolutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nct_id: str
    assets: List[TrialAssetMapping] = Field(default_factory=list)
    indications: List[TrialIndicationMapping] = Field(default_factory=list)
    biomarkers: List[TrialBiomarkerMapping] = Field(default_factory=list)
    companies: List[TrialCompanyMapping] = Field(default_factory=list)
