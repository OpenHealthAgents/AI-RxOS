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
    FUTURE_CLINICAL_RESULT = "future_clinical_result"
    FUTURE_REGULATORY_DECISION = "future_regulatory_decision"
    FUTURE_APPROVAL = "future_approval"
    FUTURE_FAILURE = "future_failure"
    FUTURE_OUTCOME_DISCLOSURE = "future_outcome_disclosure"
    FUTURE_ACQUISITION = "future_acquisition"
    FUTURE_COMPANY_EVENT = "future_company_event"
    FUTURE_LICENSING_DEAL = "future_licensing_deal"
    FUTURE_PATENT_EVENT = "future_patent_event"
    FUTURE_BIOMARKER_DISCOVERY = "future_biomarker_discovery"
    FUTURE_OBSERVATION_DATE = "future_observation_date"
    FUTURE_FEATURE_INPUT = "future_feature_input"
    FUTURE_TRAINING_SAMPLE = "future_training_sample"



# ==============================================================================
# 1. Temporal Coordinates & Evidence Metadata
# ==============================================================================

class EvidenceTemporalMetadata(BaseModel):
    """
    Complete temporal metadata tracking all 8 scientific time coordinates:
    1. publication date
    2. observation date
    3. trial date
    4. outcome date
    5. regulatory date
    6. licensing date
    7. prediction cutoff
    8. public availability date
    """
    model_config = ConfigDict(from_attributes=True)

    publication_date: Optional[date] = None
    observation_date: Optional[date] = None
    trial_date: Optional[date] = None
    outcome_date: Optional[date] = None
    regulatory_date: Optional[date] = None
    licensing_date: Optional[date] = None
    prediction_cutoff: Optional[date] = None
    public_availability_date: Optional[date] = None

    def effective_public_date(self) -> Optional[date]:
        """
        Calculates the earliest public disclosure date across public availability,
        publication, regulatory action, licensing, or outcome disclosure.
        """
        if self.public_availability_date is not None:
            return self.public_availability_date
        if self.publication_date is not None:
            return self.publication_date
        candidates = [
            d for d in [
                self.regulatory_date,
                self.licensing_date,
                self.outcome_date,
            ] if d is not None
        ]
        return min(candidates) if candidates else None

    def is_visible_at(self, cutoff_date: date) -> bool:
        """
        Evaluates strict anti-leakage visibility against an arbitrary cutoff date.
        """
        eff_date = self.effective_public_date()
        if eff_date is None:
            # Fallback to observation date or trial date if private
            fallback = self.observation_date or self.trial_date
            return fallback is not None and fallback <= cutoff_date
        return eff_date <= cutoff_date

    def get_date_by_field(self, field_name: str) -> Optional[date]:
        """Returns the specific date coordinate by field name."""
        field_map = {
            "publication_date": self.publication_date,
            "observation_date": self.observation_date,
            "trial_date": self.trial_date,
            "outcome_date": self.outcome_date,
            "regulatory_date": self.regulatory_date,
            "licensing_date": self.licensing_date,
            "prediction_cutoff": self.prediction_cutoff,
            "public_availability_date": self.public_availability_date,
        }
        return field_map.get(field_name)


class TemporalDateField(str, Enum):
    PUBLICATION_DATE = "publication_date"
    OBSERVATION_DATE = "observation_date"
    TRIAL_DATE = "trial_date"
    OUTCOME_DATE = "outcome_date"
    REGULATORY_DATE = "regulatory_date"
    LICENSING_DATE = "licensing_date"
    PREDICTION_CUTOFF = "prediction_cutoff"
    PUBLIC_AVAILABILITY_DATE = "public_availability_date"
    ANY_DATE = "any_date"


class TemporalQueryFilter(BaseModel):
    """
    Query filter enabling multidimensional time querying across evidence.
    """
    model_config = ConfigDict(from_attributes=True)

    as_of_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    date_field: TemporalDateField = TemporalDateField.ANY_DATE
    enforce_prediction_cutoff: bool = True
    prediction_cutoff: Optional[date] = None

    def matches(self, meta: EvidenceTemporalMetadata) -> bool:
        """Evaluates whether evidence temporal metadata satisfies the filter."""
        # 1. As-of date cutoff enforcement
        if self.as_of_date is not None:
            if not meta.is_visible_at(self.as_of_date):
                return False

        # 2. Prediction cutoff enforcement
        effective_cutoff = self.prediction_cutoff or (meta.prediction_cutoff if self.enforce_prediction_cutoff else None)
        if effective_cutoff is not None and self.enforce_prediction_cutoff:
            if not meta.is_visible_at(effective_cutoff):
                return False

        # 3. Specific date field range checking
        if self.date_field != TemporalDateField.ANY_DATE:
            target_date = meta.get_date_by_field(self.date_field.value)
            if target_date is None:
                return False
            if self.start_date is not None and target_date < self.start_date:
                return False
            if self.end_date is not None and target_date > self.end_date:
                return False
        else:
            # ANY_DATE range checking across all non-null coordinates
            all_dates = [
                d for d in [
                    meta.publication_date,
                    meta.observation_date,
                    meta.trial_date,
                    meta.outcome_date,
                    meta.regulatory_date,
                    meta.licensing_date,
                    meta.public_availability_date,
                ] if d is not None
            ]
            if not all_dates and (self.start_date or self.end_date):
                return False
            if self.start_date is not None:
                if not any(d >= self.start_date for d in all_dates):
                    return False
            if self.end_date is not None:
                if not any(d <= self.end_date for d in all_dates):
                    return False

        return True


class TemporalCoordinates(BaseModel):
    """
    Distinguishes all scientific temporal coordinates.
    """
    model_config = ConfigDict(from_attributes=True)
    evidence_publication_date: Optional[date] = None
    evidence_observation_date: Optional[date] = None
    trial_date: Optional[date] = None
    outcome_date: Optional[date] = None
    regulatory_date: Optional[date] = None
    licensing_date: Optional[date] = None
    prediction_cutoff_date: date
    publicly_known_date: Optional[date] = None
    public_availability_date: Optional[date] = None

    def is_visible_at_cutoff(self) -> bool:
        """
        An event or document is strictly visible ONLY if its public disclosure date
        (or publication date) occurred ON OR BEFORE the prediction cutoff date.
        """
        effective_public_date = (
            self.public_availability_date
            or self.publicly_known_date
            or self.evidence_publication_date
            or self.regulatory_date
            or self.licensing_date
            or self.outcome_date
            or self.trial_date
        )
        if effective_public_date is None:
            return False
        return effective_public_date <= self.prediction_cutoff_date

    def to_evidence_temporal_metadata(self) -> EvidenceTemporalMetadata:
        return EvidenceTemporalMetadata(
            publication_date=self.evidence_publication_date,
            observation_date=self.evidence_observation_date,
            trial_date=self.trial_date,
            outcome_date=self.outcome_date,
            regulatory_date=self.regulatory_date,
            licensing_date=self.licensing_date,
            prediction_cutoff=self.prediction_cutoff_date,
            public_availability_date=self.public_availability_date or self.publicly_known_date,
        )


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
    prediction_cutoff: Optional[date] = None
    evidence_cutoff: Optional[date] = None
    outcome_known_at_cutoff: bool = False
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

    def model_post_init(self, __context: Any) -> None:
        if self.prediction_cutoff is None:
            self.prediction_cutoff = self.cutoff.cutoff_date
        if self.evidence_cutoff is None:
            self.evidence_cutoff = self.cutoff.cutoff_date
        if not self.outcome_known_at_cutoff and len(self.known_outcomes_at_cutoff) > 0:
            self.outcome_known_at_cutoff = True


# ==============================================================================
# 7. Historical Evaluation Requests & Responses
# ==============================================================================

class HistoricalEvaluationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
    prediction_cutoff: date
    evidence_cutoff: Optional[date] = None
    strict_audit: bool = True


class HistoricalBatchEvaluationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    asset_ids: List[str]
    prediction_cutoff: date
    evidence_cutoff: Optional[date] = None
    strict_audit: bool = True


class HistoricalTimelineItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    milestone_name: str
    prediction_cutoff: date
    evidence_cutoff: date
    outcome_known_at_cutoff: bool
    stage_at_cutoff: DevelopmentStage
    owner_at_cutoff: str
    predicted_action: StrategicAction
    predicted_dps: int
    confidence: float
    known_outcomes_count: int


class HistoricalTimelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
    asset_name: str
    milestones: List[HistoricalTimelineItem]

