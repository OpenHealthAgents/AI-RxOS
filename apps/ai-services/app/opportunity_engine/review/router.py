from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.core.security import require_review_permission

from .durable_store import durable_review_store
from .service import HumanScientificReviewService

router = APIRouter(prefix="/api/v1", tags=["Human Scientific Review"])
_review_service = HumanScientificReviewService(use_durable=True)


class ReviewIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    reviewer_user_id: str | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    review_id: str
    reviewed_object_type: str
    reviewed_object_id: str
    review_action: str
    review_status: str
    rationale: str
    reviewer_user_id: str | None
    tenant_id: str | None
    model_version: str | None = None
    evidence_version: str | None = None
    original_ai_value: Any | None = None
    human_decision: Any | None = None
    original_value: Any | None = None
    corrected_value: Any | None = None


def _trusted_identity(request: Request) -> tuple[str, str]:
    return require_review_permission(request)


def _review_to_response(record: Any) -> ReviewResponse:
    return ReviewResponse(
        review_id=str(record.id),
        reviewed_object_type=record.reviewed_object_type,
        reviewed_object_id=record.reviewed_object_id,
        review_action=record.review_action.value,
        review_status=record.review_status.value,
        rationale=record.rationale,
        reviewer_user_id=record.reviewer_user_id,
        tenant_id=record.tenant_id,
        model_version=record.model_version,
        evidence_version=record.evidence_version,
        original_ai_value=record.original_ai_value,
        human_decision=record.human_decision,
        original_value=record.original_value,
        corrected_value=record.corrected_value,
    )


def _assert_trusted_reviewer(payload: dict[str, Any] | None, user_id: str) -> None:
    if payload is None:
        return
    supplied = payload.get("reviewer_user_id")
    if supplied is not None and str(supplied) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer identity must come from the trusted authenticated session.",
        )


def _get_request_context(request: Request, payload: ReviewIdentityRequest | None = None) -> tuple[str, str, str | None]:
    tenant_id, user_id = _trusted_identity(request)
    if payload is not None and payload.reviewer_user_id is not None and payload.reviewer_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer identity must come from the trusted authenticated session.")
    return tenant_id, user_id, payload.reviewer_user_id if payload is not None else None


def _require_fields(payload: dict[str, Any], *field_groups: str | tuple[str, ...]) -> None:
    for field_group in field_groups:
        alternatives = (field_group,) if isinstance(field_group, str) else field_group
        if not any(isinstance(payload.get(field), str) and payload[field].strip() for field in alternatives):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{' or '.join(alternatives)} is required.",
            )
    rationale = payload.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 10000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rationale must contain between 1 and 10000 characters.",
        )


def _durable_row_to_response(row: dict[str, Any]) -> dict[str, Any]:
    def decoded_json(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    return {
        "review_id": str(row["id"]),
        "reviewed_object_type": row["reviewed_object_type"],
        "reviewed_object_id": row["reviewed_object_id"],
        "review_action": row["review_action"],
        "review_status": row["review_status"],
        "rationale": row["rationale"],
        "reviewer_user_id": str(row["reviewer_id"]),
        "tenant_id": str(row["organization_id"]),
        "model_version": row["model_version"],
        "evidence_version": row["evidence_version"],
        "original_ai_value": decoded_json(row["original_ai_value"]),
        "human_decision": decoded_json(row["human_decision"]),
        "original_value": decoded_json(row["original_value"]),
        "corrected_value": decoded_json(row["corrected_value"]),
    }


@router.post("/reviews/evidence/approve")
@router.post("/human-review/evidence/approve")
def approve_evidence(request: Request, payload: dict[str, Any]) -> ReviewResponse:
    tenant_id, user_id, _ = _get_request_context(request, None)
    _assert_trusted_reviewer(payload, user_id)
    _require_fields(payload, ("evidence_id", "id"), "rationale")
    evidence_id = str(payload.get("evidence_id") or payload.get("id") or "")
    rationale = str(payload.get("rationale") or "")
    evidence_version = payload.get("evidence_version")
    model_version = payload.get("model_version")
    if not evidence_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Evidence ID is required.")
    record = _review_service.approve_evidence(
        evidence_id=evidence_id,
        rationale=rationale,
        reviewer_user_id=user_id,
        tenant_id=tenant_id,
        evidence_version=str(evidence_version) if evidence_version is not None else None,
        model_version=str(model_version) if model_version is not None else None,
        expected_evidence_version=payload.get("expected_evidence_version"),
    )
    return _review_to_response(record)


@router.post("/reviews/evidence/reject")
@router.post("/human-review/evidence/reject")
def reject_evidence(request: Request, payload: dict[str, Any]) -> ReviewResponse:
    tenant_id, user_id, _ = _get_request_context(request, None)
    _assert_trusted_reviewer(payload, user_id)
    _require_fields(payload, ("evidence_id", "id"), "rationale")
    evidence_id = str(payload.get("evidence_id") or payload.get("id") or "")
    rationale = str(payload.get("rationale") or "")
    record = _review_service.reject_evidence(
        evidence_id=evidence_id,
        rationale=rationale,
        reviewer_user_id=user_id,
        tenant_id=tenant_id,
        evidence_version=str(payload.get("evidence_version")) if payload.get("evidence_version") is not None else None,
        model_version=str(payload.get("model_version")) if payload.get("model_version") is not None else None,
    )
    return _review_to_response(record)


@router.post("/reviews/evidence")
@router.post("/human-review/evidence")
def add_evidence(request: Request, payload: dict[str, Any]) -> ReviewResponse:
    tenant_id, user_id, _ = _get_request_context(request, None)
    _assert_trusted_reviewer(payload, user_id)
    _require_fields(payload, "asset_id", "rationale")
    asset_id = payload.get("asset_id")
    evidence_payload = payload.get("evidence") or payload.get("evidence_payload") or {}
    if not isinstance(evidence_payload, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Evidence payload must be an object.")
    record = _review_service.add_evidence(
        asset_id=str(asset_id),
        evidence_payload=evidence_payload,
        provenance=payload.get("provenance") or {},
        rationale=str(payload.get("rationale") or "Human evidence submission"),
        reviewer_user_id=user_id,
        tenant_id=tenant_id,
        source_type=str(payload.get("source_type") or "human_submission"),
        model_version=str(payload.get("model_version")) if payload.get("model_version") is not None else None,
        evidence_version=str(payload.get("evidence_version")) if payload.get("evidence_version") is not None else None,
    )
    return _review_to_response(record)


@router.post("/reviews/evidence/quality")
@router.post("/human-review/evidence/quality")
def change_evidence_quality(request: Request, payload: dict[str, Any]) -> ReviewResponse:
    tenant_id, user_id, _ = _get_request_context(request, None)
    _assert_trusted_reviewer(payload, user_id)
    _require_fields(payload, "evidence_id", "new_quality", "rationale")
    record = _review_service.change_evidence_quality(
        evidence_id=str(payload.get("evidence_id") or payload.get("id") or ""),
        previous_quality=payload.get("previous_quality"),
        new_quality=payload.get("new_quality"),
        rationale=str(payload.get("rationale") or ""),
        reviewer_user_id=user_id,
        tenant_id=tenant_id,
        evidence_version=str(payload.get("evidence_version")) if payload.get("evidence_version") is not None else None,
        model_version=str(payload.get("model_version")) if payload.get("model_version") is not None else None,
    )
    return _review_to_response(record)


@router.post("/reviews/entities/correct")
@router.post("/human-review/entities/correct")
def correct_entity(request: Request, payload: dict[str, Any]) -> ReviewResponse:
    tenant_id, user_id, _ = _get_request_context(request, None)
    _assert_trusted_reviewer(payload, user_id)
    _require_fields(payload, ("reviewed_entity_id", "entity_id"), ("corrected_entity_id", "target_entity_id"), "rationale")
    record = _review_service.correct_entity(
        reviewed_entity_id=str(payload.get("reviewed_entity_id") or payload.get("entity_id") or ""),
        corrected_entity_id=str(payload.get("corrected_entity_id") or payload.get("target_entity_id") or ""),
        rationale=str(payload.get("rationale") or ""),
        reviewer_user_id=user_id,
        tenant_id=tenant_id,
        original_entity_id=payload.get("original_entity_id"),
        model_version=str(payload.get("model_version")) if payload.get("model_version") is not None else None,
        evidence_version=str(payload.get("evidence_version")) if payload.get("evidence_version") is not None else None,
    )
    return _review_to_response(record)


@router.post("/reviews/classifications/correct")
@router.post("/human-review/classifications/correct")
def correct_classification(request: Request, payload: dict[str, Any]) -> ReviewResponse:
    tenant_id, user_id, _ = _get_request_context(request, None)
    _assert_trusted_reviewer(payload, user_id)
    _require_fields(payload, "reviewed_object_id", "original_classification", "corrected_classification", "rationale")
    record = _review_service.correct_classification(
        reviewed_object_id=str(payload.get("reviewed_object_id") or payload.get("classification_id") or ""),
        original_classification=str(payload.get("original_classification") or ""),
        corrected_classification=str(payload.get("corrected_classification") or ""),
        rationale=str(payload.get("rationale") or ""),
        reviewer_user_id=user_id,
        tenant_id=tenant_id,
        model_version=str(payload.get("model_version")) if payload.get("model_version") is not None else None,
        evidence_version=str(payload.get("evidence_version")) if payload.get("evidence_version") is not None else None,
    )
    return _review_to_response(record)


@router.post("/reviews/predictions/review")
@router.post("/human-review/predictions/review")
def review_prediction(request: Request, payload: dict[str, Any]) -> ReviewResponse:
    tenant_id, user_id, _ = _get_request_context(request, None)
    _assert_trusted_reviewer(payload, user_id)
    _require_fields(payload, "prediction_id", "rationale")
    record = _review_service.review_prediction(
        prediction_id=str(payload.get("prediction_id") or ""),
        original_prediction=payload.get("original_prediction"),
        review_outcome=str(payload.get("review_outcome") or "accepted"),
        rationale=str(payload.get("rationale") or ""),
        reviewer_user_id=user_id,
        tenant_id=tenant_id,
        model_version=str(payload.get("model_version")) if payload.get("model_version") is not None else None,
        evidence_version=str(payload.get("evidence_version")) if payload.get("evidence_version") is not None else None,
    )
    return _review_to_response(record)


@router.post("/reviews/recommendations/override")
@router.post("/human-review/recommendations/override")
def override_recommendation(request: Request, payload: dict[str, Any]) -> ReviewResponse:
    tenant_id, user_id, _ = _get_request_context(request, None)
    _assert_trusted_reviewer(payload, user_id)
    _require_fields(payload, "recommendation_id", "original_recommendation", "human_decision", "rationale")
    record = _review_service.override_recommendation(
        recommendation_id=str(payload.get("recommendation_id") or ""),
        original_recommendation=str(payload.get("original_recommendation") or ""),
        human_decision=str(payload.get("human_decision") or ""),
        rationale=str(payload.get("rationale") or ""),
        reviewer_user_id=user_id,
        tenant_id=tenant_id,
        model_version=str(payload.get("model_version")) if payload.get("model_version") is not None else None,
        evidence_version=str(payload.get("evidence_version")) if payload.get("evidence_version") is not None else None,
        expected_model_version=str(payload.get("expected_model_version")) if payload.get("expected_model_version") is not None else None,
        expected_evidence_version=str(payload.get("expected_evidence_version")) if payload.get("expected_evidence_version") is not None else None,
    )
    return _review_to_response(record)


@router.get("/reviews/history")
@router.get("/human-review/history")
async def list_reviews(request: Request, tenant_id: str | None = None, reviewed_object_type: str | None = None) -> list[ReviewResponse]:
    trusted_tenant, _ = _trusted_identity(request)
    if tenant_id is not None and tenant_id != trusted_tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is not allowed.")
    records = await durable_review_store.list_reviews(
        tenant_id=trusted_tenant,
        reviewed_object_type=reviewed_object_type,
    )
    return [ReviewResponse(**_durable_row_to_response(record)) for record in records]
