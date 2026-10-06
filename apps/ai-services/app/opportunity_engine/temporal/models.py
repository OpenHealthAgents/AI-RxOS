from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.domain.canonical_model import (
    DevelopmentStage,
    EvidencePolarity,
    ScientificEvidenceState,
    StrategicAction,
)
from app.opportunity_engine.domain.schemas import StageTransitionProbabilities


class OutcomeType(str, Enum):
    TRIAL_READOUT = "trial_readout"
    TRIAL_FAILURE = "trial_failure"
    REGULATORY_APPROVAL = "regulatory_approval"
    COMPLETE_RESPONSE_LETTER = "complete_response_letter"
    ADVISORY_COMMITTEE_VOTE = "advisory_committee_vote"
    COMPANY_ACQUISITION = "company_acquisition"
    LICENSING_DEAL = "licensing_deal"
    BIOMARKER_DISCOVERY = "biomarker_discovery"
    CLINICAL_HOLD = "clinical_hold"
    BLACK_BOX_WARNING = "black_box_warning"


class LeakageViolationType(str, Enum):
    FUTURE_PUBLICATION = "future_publication"
    FUTURE_TRIAL_RESULT = "future_trial_result"
    FUTURE_REGULATORY_DECISION = "future_regulatory_decision"
    FUTURE_OUTCOME_DISCLOSURE = "future_outcome_disclosure"
    FUTURE_ACQUISITION = "future_acquisition"
    FUTURE_LICENSING_DEAL = "future_licensing_deal"
    FUTURE_BIOMARKER_DISCOVERY = "future_biomarker_discovery"
    FUTURE_OBSERVATION_DATE = "future_observation_date"


# ==============================================================================
# 1. Temporal Coordinates
# ==============================================================================

class TemporalCoordinates(BaseModel):
    """
    Distinguishes the 7 distinct temporal coordinates for scientific data.
    """
    model_config = ConfigDict(from_attributes=True)
    evidence_publication_date: Optional[date] = None
    evidence_observation_date: Optional[date] = None
    trial_date: Optional[date] = None
    outcome_date: Optional[date] = None
    regulatory_date: Optional[date] = None
    prediction_cutoff_date: date
    publicly_known_date: Optional[date] = None

    def is_visible_at_cutoff(self) -> bool:
        """
        An event or document is strictly visible ONLY if its public disclosure date
        (or publication date) occurred ON OR BEFORE the prediction cutoff date.
        """
        effective_public_date = self.publicly_known_date or self.evidence_publication_date or self.regulatory_date or self.trial_date
        if effective_public_date is None:
            return False
        return effective_public_date <= self.prediction_cutoff_date


# ==============================================================================
# 2. EvidenceCutoff
# ==============================================================================

class EvidenceCutoff(BaseModel):
    """
    Temporal boundary specifying what evidence is legally and scientifically
    admissible for a historical simulation.
    """
    model_config = ConfigDict(from_attributes=True)
    cutoff_date: date
    enforce_strict_publication_boundary: bool = True
    enforce_strict_public_disclosure_boundary: bool = True
    description: Optional[str] = None

    def is_admissible(
        self,
        event_date: Optional[date],
        public_disclosure_date: Optional[date] = None,
    ) -> bool:
        """
        Evaluates admissibility against cutoff. If either disclosure date or event date
        is in the future, it is strictly inadmissible.
        """
        if public_disclosure_date and public_disclosure_date > self.cutoff_date:
            return False
        if event_date and event_date > self.cutoff_date:
            return False
        return True


# ==============================================================================
# 3. OutcomeAvailability
# ==============================================================================

class OutcomeAvailability(BaseModel):
    """
    Tracks an outcome event along with the critical date when it actually
    became publicly known to the scientific community and markets.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    outcome_type: OutcomeType
    headline: str
    description: str
    event_date: date
    publicly_known_date: date
    disclosure_source: str
    disclosure_url: Optional[str] = None
    is_favorable: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def is_available_at(self, cutoff_date: date) -> bool:
        """
        Determines whether the outcome was publicly known as of the cutoff date.
        """
        return self.publicly_known_date <= cutoff_date


# ==============================================================================
# 4. Leakage Violation & Audit
# ==============================================================================

class LeakageViolation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    violation_type: LeakageViolationType
    entity_id: str
    entity_name: str
    entity_date: date
    cutoff_date: date
    days_post_cutoff: int
    details: str


class LeakageAuditReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    asset_id: UUID
    cutoff_date: date
    audit_passed: bool
    total_eligible_items: int
    total_suppressed_items: int
    violations: List[LeakageViolation] = Field(default_factory=list)
    audit_hash: str
    audit_timestamp: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 5. PredictionSnapshot
# ==============================================================================

class PredictionSnapshot(BaseModel):
    """
    Deterministic frozen model prediction evaluated at cutoff.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    cutoff_date: date
    model_name: str = "CalibratedBayesianOpportunityEngine"
    model_version: str = "v0.1-historical"
    input_feature_hash: str
    predicted_action: StrategicAction
    predicted_dps: int = Field(ge=0, le=100)
    predicted_transitions: StageTransitionProbabilities
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    eligible_evidence_count: int
    suppressed_future_evidence_count: int
    anti_leakage_audit_passed: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# 6. HistoricalSnapshot
# ==============================================================================

class HistoricalSnapshot(BaseModel):
    """
    Complete frozen snapshot of an asset at an exact historical date,
    guaranteeing zero exposure of later publications, trial readouts,
    approvals, failures, acquisitions, or licensing events.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    asset_name: str
    cutoff: EvidenceCutoff
    stage_at_cutoff: DevelopmentStage
    owner_at_cutoff: str
    indication_at_cutoff: str
    prediction: PredictionSnapshot
    known_outcomes_at_cutoff: List[OutcomeAvailability] = Field(default_factory=list)
    suppressed_future_outcomes: List[OutcomeAvailability] = Field(default_factory=list)
    ground_truth_post_cutoff_outcome: Optional[str] = None
    accuracy_assessment: Optional[str] = None
    audit_report: LeakageAuditReport
    created_at: datetime = Field(default_factory=datetime.utcnow)
