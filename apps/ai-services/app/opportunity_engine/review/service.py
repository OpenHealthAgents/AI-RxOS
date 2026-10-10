from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID

from app.opportunity_engine.data.fixtures import get_fixture_asset

from .durable_store import durable_review_store
from .models import HumanScientificReviewAction, ReviewRecord, ReviewStatus


class HumanScientificReviewService:
    """Durable review records for AI output review and override workflows.

    When use_durable=True and kg_canonical_database_url is configured,
    reviews are persisted to the canonical PostgreSQL database via KG decision_governance.
    Defaults to in-memory storage for backward compatibility. Set use_durable=True
    explicitly to enable durable persistence.
    """

    def __init__(self, use_durable: bool = False) -> None:
        self._reviews: dict[str, ReviewRecord] = {}
        self._evidence_versions: dict[str, str | None] = {}
        self._decision_versions: dict[str, str | None] = {}
        self._use_durable = use_durable

    def list_reviews(self, *, tenant_id: str | None = None, reviewed_object_type: str | None = None) -> list[ReviewRecord]:
        records = list(self._reviews.values())
        if tenant_id is not None:
            records = [record for record in records if record.tenant_id == tenant_id]
        if reviewed_object_type is not None:
            records = [record for record in records if record.reviewed_object_type == reviewed_object_type]
        return sorted(records, key=lambda record: record.review_timestamp)

    def get_review(self, review_id: UUID | str) -> ReviewRecord | None:
        review_key = str(review_id)
        return self._reviews.get(review_key)

    def _idempotency_key(
        self,
        *,
        reviewed_object_type: str,
        reviewed_object_id: str,
        review_action: HumanScientificReviewAction,
        reviewer_user_id: str,
        rationale: str,
        tenant_id: str | None,
    ) -> str:
        payload = "|".join([
            reviewed_object_type,
            str(reviewed_object_id),
            review_action.value,
            str(reviewer_user_id),
            rationale,
            str(tenant_id or ""),
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _existing_review(
        self,
        *,
        reviewed_object_type: str,
        reviewed_object_id: str,
        review_action: HumanScientificReviewAction,
        reviewer_user_id: str,
        rationale: str,
        tenant_id: str | None,
    ) -> ReviewRecord | None:
        key = self._idempotency_key(
            reviewed_object_type=reviewed_object_type,
            reviewed_object_id=reviewed_object_id,
            review_action=review_action,
            reviewer_user_id=reviewer_user_id,
            rationale=rationale,
            tenant_id=tenant_id,
        )
        for record in self._reviews.values():
            if record.idempotency_key == key:
                return record
        return None

    def _record_review(
        self,
        *,
        reviewed_object_type: str,
        reviewed_object_id: str,
        review_action: HumanScientificReviewAction,
        original_ai_value: Any | None,
        human_decision: Any | None,
        original_value: Any | None,
        corrected_value: Any | None,
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None,
        model_version: str | None = None,
        evidence_version: str | None = None,
        decision_version: str | None = None,
        source_provenance: dict[str, Any] | None = None,
        previous_review_id: UUID | None = None,
        review_status: ReviewStatus | None = None,
    ) -> ReviewRecord:
        if not rationale or not rationale.strip():
            raise ValueError("Rationale is required for human review decisions.")

        existing = self._existing_review(
            reviewed_object_type=reviewed_object_type,
            reviewed_object_id=reviewed_object_id,
            review_action=review_action,
            reviewer_user_id=reviewer_user_id,
            rationale=rationale,
            tenant_id=tenant_id,
        )
        if existing is not None:
            return existing

        record = ReviewRecord(
            reviewed_object_type=reviewed_object_type,
            reviewed_object_id=str(reviewed_object_id),
            review_action=review_action,
            review_status=review_status or (ReviewStatus.APPROVED if review_action in {HumanScientificReviewAction.APPROVE_EVIDENCE, HumanScientificReviewAction.REVIEW_PREDICTION} else ReviewStatus.ACTIVE),
            original_ai_value=original_ai_value,
            human_decision=human_decision,
            original_value=original_value,
            corrected_value=corrected_value,
            rationale=rationale.strip(),
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            decision_version=decision_version,
            source_provenance=source_provenance or {},
            previous_review_id=previous_review_id,
            idempotency_key=self._idempotency_key(
                reviewed_object_type=reviewed_object_type,
                reviewed_object_id=reviewed_object_id,
                review_action=review_action,
                reviewer_user_id=reviewer_user_id,
                rationale=rationale,
                tenant_id=tenant_id,
            ),
        )
        if self._use_durable:
            if not tenant_id:
                raise ValueError("tenant_id is required for durable human review storage")
            durable_result = durable_review_store.create_review_sync(
                reviewed_object_type=reviewed_object_type,
                reviewed_object_id=reviewed_object_id,
                review_action=review_action.value,
                review_status=record.review_status.value,
                rationale=rationale.strip(),
                original_ai_value=original_ai_value,
                human_decision=human_decision,
                original_value=original_value,
                corrected_value=corrected_value,
                reviewer_user_id=reviewer_user_id,
                tenant_id=tenant_id,
                model_version=model_version,
                evidence_version=evidence_version,
                decision_version=decision_version,
                source_provenance=source_provenance,
                previous_review_id=str(previous_review_id) if previous_review_id else None,
            )
            if durable_result is None:
                raise RuntimeError(
                    "Durable review persistence failed. Review was not saved to the canonical database. "
                    "Check kg_canonical_database_url configuration and database availability."
                )
            record.id = UUID(str(durable_result["id"]))
            record.review_timestamp = durable_result["created_at"]

        self._reviews[str(record.id)] = record

        return record

    def approve_evidence(
        self,
        evidence_id: str,
        *,
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None = None,
        evidence_version: str | None = None,
        model_version: str | None = None,
        expected_evidence_version: str | None = None,
    ) -> ReviewRecord:
        if expected_evidence_version is not None:
            current = self._evidence_versions.get(evidence_id)
            if current is not None and current != expected_evidence_version:
                raise ValueError("Evidence version is stale.")
        if not evidence_id or not evidence_id.strip():
            raise ValueError("Evidence ID is required.")
        record = self._record_review(
            reviewed_object_type="evidence",
            reviewed_object_id=evidence_id,
            review_action=HumanScientificReviewAction.APPROVE_EVIDENCE,
            original_ai_value={"evidence_id": evidence_id, "approved": True},
            human_decision="approved",
            original_value={"evidence_id": evidence_id},
            corrected_value=None,
            rationale=rationale,
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            source_provenance={"evidence_id": evidence_id},
            review_status=ReviewStatus.APPROVED,
        )
        if evidence_version is not None:
            self._evidence_versions[evidence_id] = evidence_version
        return record

    def reject_evidence(
        self,
        evidence_id: str,
        *,
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None = None,
        evidence_version: str | None = None,
        model_version: str | None = None,
    ) -> ReviewRecord:
        if not evidence_id or not evidence_id.strip():
            raise ValueError("Evidence ID is required.")
        record = self._record_review(
            reviewed_object_type="evidence",
            reviewed_object_id=evidence_id,
            review_action=HumanScientificReviewAction.REJECT_EVIDENCE,
            original_ai_value={"evidence_id": evidence_id, "rejected": False},
            human_decision="rejected",
            original_value={"evidence_id": evidence_id},
            corrected_value=None,
            rationale=rationale,
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            review_status=ReviewStatus.REJECTED,
            source_provenance={"evidence_id": evidence_id},
        )
        if evidence_version is not None:
            self._evidence_versions[evidence_id] = evidence_version
        return record

    def add_evidence(
        self,
        *,
        asset_id: str,
        evidence_payload: dict[str, Any],
        provenance: dict[str, Any],
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None = None,
        source_type: str = "human_submission",
        model_version: str | None = None,
        evidence_version: str | None = None,
    ) -> ReviewRecord:
        if not asset_id or not asset_id.strip():
            raise ValueError("Asset ID is required.")
        if not isinstance(evidence_payload, dict) or "title" not in evidence_payload:
            raise ValueError("Human-submitted evidence requires a title and source fields.")
        evidence_id = str(evidence_payload.get("evidence_id") or f"human-evidence:{asset_id}:{datetime.utcnow().timestamp()}")
        record = self._record_review(
            reviewed_object_type="evidence",
            reviewed_object_id=evidence_id,
            review_action=HumanScientificReviewAction.ADD_EVIDENCE,
            original_ai_value={"asset_id": asset_id, "source_type": source_type},
            human_decision="added",
            original_value=None,
            corrected_value=evidence_payload,
            rationale=rationale,
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            review_status=ReviewStatus.ACTIVE,
            source_provenance={"asset_id": asset_id, **provenance},
        )
        if evidence_version is not None:
            self._evidence_versions[evidence_id] = evidence_version
        return record

    def correct_entity(
        self,
        *,
        reviewed_entity_id: str,
        corrected_entity_id: str,
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None = None,
        original_entity_id: str | None = None,
        model_version: str | None = None,
        evidence_version: str | None = None,
    ) -> ReviewRecord:
        if not corrected_entity_id or not corrected_entity_id.strip():
            raise ValueError("Corrected entity ID is required.")
        if get_fixture_asset(corrected_entity_id.lower()) is None:
            raise ValueError(f"Entity '{corrected_entity_id}' is not a valid accessible entity.")
        record = self._record_review(
            reviewed_object_type="entity",
            reviewed_object_id=str(reviewed_entity_id),
            review_action=HumanScientificReviewAction.CORRECT_ENTITY,
            original_ai_value={"entity_id": reviewed_entity_id},
            human_decision="corrected_entity",
            original_value=original_entity_id or reviewed_entity_id,
            corrected_value=corrected_entity_id,
            rationale=rationale,
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            review_status=ReviewStatus.CORRECTED,
            source_provenance={"original_entity_id": original_entity_id or reviewed_entity_id, "corrected_entity_id": corrected_entity_id},
        )
        return record

    def correct_classification(
        self,
        *,
        reviewed_object_id: str,
        original_classification: str,
        corrected_classification: str,
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None = None,
        model_version: str | None = None,
        evidence_version: str | None = None,
    ) -> ReviewRecord:
        if not corrected_classification or not corrected_classification.strip():
            raise ValueError("Corrected classification is required.")
        return self._record_review(
            reviewed_object_type="classification",
            reviewed_object_id=str(reviewed_object_id),
            review_action=HumanScientificReviewAction.CORRECT_CLASSIFICATION,
            original_ai_value={"classification": original_classification},
            human_decision=corrected_classification,
            original_value=original_classification,
            corrected_value=corrected_classification,
            rationale=rationale,
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            review_status=ReviewStatus.CORRECTED,
            source_provenance={"original_classification": original_classification, "corrected_classification": corrected_classification},
        )

    def change_evidence_quality(
        self,
        *,
        evidence_id: str,
        previous_quality: str | float | None,
        new_quality: str | float,
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None = None,
        evidence_version: str | None = None,
        model_version: str | None = None,
    ) -> ReviewRecord:
        if not evidence_id or not evidence_id.strip():
            raise ValueError("Evidence ID is required.")
        return self._record_review(
            reviewed_object_type="evidence_quality",
            reviewed_object_id=str(evidence_id),
            review_action=HumanScientificReviewAction.CHANGE_EVIDENCE_QUALITY,
            original_ai_value={"previous_quality": previous_quality},
            human_decision=new_quality,
            original_value=previous_quality,
            corrected_value=new_quality,
            rationale=rationale,
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            review_status=ReviewStatus.ACTIVE,
            source_provenance={"previous_quality": previous_quality, "new_quality": new_quality},
        )

    def review_prediction(
        self,
        *,
        prediction_id: str,
        original_prediction: Any,
        review_outcome: str,
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None = None,
        model_version: str | None = None,
        evidence_version: str | None = None,
    ) -> ReviewRecord:
        if not prediction_id or not prediction_id.strip():
            raise ValueError("Prediction ID is required.")
        return self._record_review(
            reviewed_object_type="prediction",
            reviewed_object_id=str(prediction_id),
            review_action=HumanScientificReviewAction.REVIEW_PREDICTION,
            original_ai_value=original_prediction,
            human_decision=review_outcome,
            original_value=original_prediction,
            corrected_value=None,
            rationale=rationale,
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            review_status=ReviewStatus.APPROVED,
            source_provenance={"prediction_id": prediction_id, "review_outcome": review_outcome},
        )

    def override_recommendation(
        self,
        *,
        recommendation_id: str,
        original_recommendation: str,
        human_decision: str,
        rationale: str,
        reviewer_user_id: str,
        tenant_id: str | None = None,
        model_version: str | None = None,
        evidence_version: str | None = None,
        expected_model_version: str | None = None,
        expected_evidence_version: str | None = None,
    ) -> ReviewRecord:
        if expected_model_version is not None:
            current = self._decision_versions.get(recommendation_id)
            if current is not None and current != expected_model_version:
                raise ValueError("Decision model version is stale.")
        if not recommendation_id or not recommendation_id.strip():
            raise ValueError("Recommendation ID is required.")
        record = self._record_review(
            reviewed_object_type="recommendation",
            reviewed_object_id=str(recommendation_id),
            review_action=HumanScientificReviewAction.OVERRIDE_RECOMMENDATION,
            original_ai_value=original_recommendation,
            human_decision=human_decision,
            original_value=original_recommendation,
            corrected_value=human_decision,
            rationale=rationale,
            reviewer_user_id=reviewer_user_id,
            tenant_id=tenant_id,
            model_version=model_version,
            evidence_version=evidence_version,
            decision_version=expected_model_version or model_version,
            review_status=ReviewStatus.OVERRIDDEN,
            source_provenance={
                "recommendation_id": recommendation_id,
                "original_recommendation": original_recommendation,
                "human_decision": human_decision,
            },
        )
        if model_version is not None:
            self._decision_versions[recommendation_id] = model_version
        if evidence_version is not None:
            self._evidence_versions[recommendation_id] = evidence_version
        return record
