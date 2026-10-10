from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HumanScientificReviewAction(str, Enum):
    APPROVE_EVIDENCE = "approve_evidence"
    REJECT_EVIDENCE = "reject_evidence"
    CORRECT_ENTITY = "correct_entity"
    CORRECT_CLASSIFICATION = "correct_classification"
    ADD_EVIDENCE = "add_evidence"
    CHANGE_EVIDENCE_QUALITY = "change_evidence_quality"
    REVIEW_PREDICTION = "review_prediction"
    OVERRIDE_RECOMMENDATION = "override_recommendation"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"
    OVERRIDDEN = "overridden"
    ACTIVE = "active"
    INVALID = "invalid"


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID = Field(default_factory=uuid4)
    reviewed_object_type: str
    reviewed_object_id: str
    review_action: HumanScientificReviewAction
    review_status: ReviewStatus = ReviewStatus.ACTIVE
    original_ai_value: Any | None = None
    human_decision: Any | None = None
    original_value: Any | None = None
    corrected_value: Any | None = None
    rationale: str = ""
    reviewer_user_id: str | None = None
    tenant_id: str | None = None
    review_timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_version: str | None = None
    evidence_version: str | None = None
    decision_version: str | None = None
    source_provenance: dict[str, Any] = Field(default_factory=dict)
    previous_review_id: UUID | None = None
    idempotency_key: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_rationale(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        rationale = data.get("rationale")
        if rationale is not None and not isinstance(rationale, str):
            data["rationale"] = str(rationale)
        return data
