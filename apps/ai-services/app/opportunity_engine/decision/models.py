from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class DecisionAction(str, Enum):
    PURSUE = "PURSUE"
    PARTNER = "PARTNER"
    LICENSE = "LICENSE"
    MONITOR = "MONITOR"
    AVOID = "AVOID"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DecisionPolicy(BaseModel):
    """Explicit, reproducible, configurable decision policy for opportunity selection."""

    name: str = "phase_11_master_decision_policy"
    version: str = "v1.0"
    min_confidence: float = 0.45
    evidence_quality_floor: float = 0.35
    pursue_score_floor: float = 80.0
    partner_score_floor: float = 70.0
    license_score_floor: float = 64.0
    monitor_score_floor: float = 48.0
    avoid_score_floor: float = 36.0
    unknown_penalty: float = 12.0
    contradiction_penalty: float = 10.0
    critical_evidence_keys: list[str] = Field(
        default_factory=lambda: ["safety", "licensing", "commercial", "patient", "cns"]
    )


class DecisionRequest(BaseModel):
    asset_id: str
    tenant_id: str | None = None
    evaluation_cutoff: date | str | None = None
    policy: DecisionPolicy | None = None
    biology: dict[str, Any] | None = None
    clinical: dict[str, Any] | None = None
    cns: dict[str, Any] | None = None
    patient: dict[str, Any] | None = None
    safety: dict[str, Any] | None = None
    resistance: dict[str, Any] | None = None
    combination: dict[str, Any] | None = None
    competition: dict[str, Any] | None = None
    licensing: dict[str, Any] | None = None
    commercial: dict[str, Any] | None = None
    evidence_quality: dict[str, Any] | None = None
    ml_predictions: dict[str, Any] | None = None
    source_evidence: list[dict[str, Any]] | None = None
    contradictory_evidence: list[dict[str, Any]] | None = None
    unknowns: list[str] | None = None


class MasterDecisionRequest(DecisionRequest):
    pass


class DecisionResult(BaseModel):
    asset_id: str
    tenant_id: str | None = None
    evaluation_cutoff: date
    decision: DecisionAction
    priority: Literal["P1", "P2", "P3", "P4"]
    score: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradictory_evidence: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    recommended_action: str
    policy_name: str
    policy_version: str
    decision_timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_versions: dict[str, str] = Field(default_factory=dict)
    feature_versions: dict[str, str] = Field(default_factory=dict)
    evidence_quality: float | None = None
    upstream_signal_availability: dict[str, str] = Field(default_factory=dict)


class MasterDecisionResult(DecisionResult):
    pass
