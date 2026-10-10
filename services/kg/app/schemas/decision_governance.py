from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

DecisionActionValue = Literal[
    "PURSUE",
    "INVESTIGATE",
    "PARTNER",
    "LICENSE",
    "MONITOR",
    "AVOID",
    "INSUFFICIENT_EVIDENCE",
]
ReviewActionValue = Literal["approve", "reject", "correct", "override"]
ReviewStatusValue = Literal["approved", "rejected", "corrected", "overridden"]


class DecisionSnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=200)
    action: DecisionActionValue
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evaluation_cutoff: AwareDatetime
    policy_name: str = Field(min_length=1, max_length=200)
    policy_version: str = Field(min_length=1, max_length=120)
    prompt_version: str | None = Field(default=None, max_length=120)
    model_versions: dict[str, str] = Field(default_factory=dict)
    feature_versions: dict[str, str] = Field(default_factory=dict)
    signal_payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    explanation: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key", "policy_name", "policy_version", "prompt_version")
    @classmethod
    def require_non_whitespace(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("value must not be blank")
        return value.strip() if value else None


class DecisionReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=200)
    review_action: ReviewActionValue
    review_status: ReviewStatusValue
    rationale: str = Field(min_length=1, max_length=10000)
    original_ai_value: Any
    human_decision: Any
    model_version: str | None = Field(default=None, max_length=120)
    evidence_version: str | None = Field(default=None, max_length=120)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key", "rationale")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class DecisionHistoryPage(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    as_of: datetime | None = None
