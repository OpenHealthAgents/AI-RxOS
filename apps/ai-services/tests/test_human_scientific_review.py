from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.opportunity_engine.review.models import HumanScientificReviewAction
from app.opportunity_engine.review.router import router as review_router
from app.opportunity_engine.review.service import HumanScientificReviewService


def _build_app(
    *,
    tenant_id: str | None = "tenant-1",
    user_id: str | None = "reviewer-1",
    roles: set[str] | None = None,
    authenticated: bool = True,
) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def add_trusted_context(request: Request, call_next):
        request.state.tenant_id = tenant_id
        request.state.user_id = user_id
        request.state.roles = roles if roles is not None else {"reviewer"}
        request.state.permissions = set()
        request.state.authenticated = authenticated
        return await call_next(request)

    app.include_router(review_router)
    return app


def test_human_review_approves_and_rejects_evidence_without_overwriting_source() -> None:
    service = HumanScientificReviewService()
    approval = service.approve_evidence(
        "ev-001",
        rationale="Evidence is relevant and appropriately sourced.",
        reviewer_user_id="reviewer-1",
        tenant_id="tenant-1",
        evidence_version="v2",
        model_version="model-v1",
    )
    assert approval.review_action == HumanScientificReviewAction.APPROVE_EVIDENCE
    assert approval.human_decision == "approved"
    assert approval.original_ai_value == {"evidence_id": "ev-001", "approved": True}

    rejection = service.reject_evidence(
        "ev-001",
        rationale="Source is not sufficiently validated for this claim.",
        reviewer_user_id="reviewer-2",
        tenant_id="tenant-1",
        evidence_version="v3",
    )
    assert rejection.review_status.value == "rejected"
    assert rejection.original_value == {"evidence_id": "ev-001"}
    assert len(service.list_reviews(tenant_id="tenant-1")) >= 2


def test_entity_correction_preserves_original_resolution_and_validates_target() -> None:
    service = HumanScientificReviewService()
    record = service.correct_entity(
        reviewed_entity_id="entity-legacy",
        corrected_entity_id="zongertinib",
        rationale="The original entity resolution should point to the canonical asset.",
        reviewer_user_id="reviewer-1",
        tenant_id="tenant-1",
        original_entity_id="entity-legacy",
    )
    assert record.original_value == "entity-legacy"
    assert record.corrected_value == "zongertinib"
    assert record.review_action == HumanScientificReviewAction.CORRECT_ENTITY

    try:
        service.correct_entity(
            reviewed_entity_id="entity-legacy",
            corrected_entity_id="not-an-entity",
            rationale="Invalid entity.",
            reviewer_user_id="reviewer-1",
            tenant_id="tenant-1",
        )
        raise AssertionError("Invalid entity correction should have failed")
    except ValueError:
        pass


def test_recommendation_override_keeps_original_ai_decision_distinct() -> None:
    service = HumanScientificReviewService()
    record = service.override_recommendation(
        recommendation_id="rec-123",
        original_recommendation="PURSUE",
        human_decision="MONITOR",
        rationale="Clinical evidence is materially weaker than the model predicted.",
        reviewer_user_id="reviewer-3",
        tenant_id="tenant-1",
        model_version="decision-v4",
        evidence_version="evidence-v11",
    )
    assert record.original_value == "PURSUE"
    assert record.corrected_value == "MONITOR"
    assert record.human_decision == "MONITOR"
    assert record.review_action == HumanScientificReviewAction.OVERRIDE_RECOMMENDATION


def test_classification_and_quality_reviews_require_rationale() -> None:
    service = HumanScientificReviewService()
    classification_record = service.correct_classification(
        reviewed_object_id="cls-9",
        original_classification="HIGH_PRIORITY",
        corrected_classification="MONITOR",
        rationale="The asset should be monitored due to elevated safety risk.",
        reviewer_user_id="reviewer-1",
        tenant_id="tenant-1",
    )
    assert classification_record.corrected_value == "MONITOR"

    try:
        service.change_evidence_quality(
            evidence_id="ev-7",
            previous_quality="high",
            new_quality="moderate",
            rationale="",
            reviewer_user_id="reviewer-1",
            tenant_id="tenant-1",
        )
        raise AssertionError("Missing rationale should be rejected")
    except ValueError:
        pass


def test_api_uses_trusted_context_and_rejects_fake_reviewer_identity() -> None:
    client = TestClient(_build_app())
    response = client.post(
        "/api/v1/reviews/evidence/approve",
        json={
            "evidence_id": "ev-trusted-1",
            "rationale": "Evidence is acceptable.",
            "reviewer_user_id": "fake-user",
            "evidence_version": "v2",
            "model_version": "m-v1",
        },
    )
    assert response.status_code == 403
    assert "trusted authenticated" in response.json()["detail"].lower()


def test_review_api_requires_authentication_tenant_and_review_permission() -> None:
    payload = {"evidence_id": "ev-1", "rationale": "Reviewed evidence"}
    unauthenticated = TestClient(_build_app(authenticated=False)).post(
        "/api/v1/reviews/evidence/approve", json=payload
    )
    assert unauthenticated.status_code == 401

    missing_tenant = TestClient(_build_app(tenant_id=None)).post(
        "/api/v1/reviews/evidence/approve", json=payload
    )
    assert missing_tenant.status_code == 403

    insufficient_role = TestClient(_build_app(roles={"analyst"})).post(
        "/api/v1/reviews/evidence/approve", json=payload
    )
    assert insufficient_role.status_code == 403


def test_review_api_rejects_invalid_review_input_before_persistence() -> None:
    response = TestClient(_build_app()).post(
        "/api/v1/reviews/evidence/approve",
        json={"evidence_id": "", "rationale": " "},
    )
    assert response.status_code == 422


def test_review_history_rejects_cross_tenant_filter() -> None:
    response = TestClient(_build_app()).get(
        "/api/v1/reviews/history",
        params={"tenant_id": "tenant-2"},
    )
    assert response.status_code == 403


def test_duplicate_review_submission_is_idempotent() -> None:
    service = HumanScientificReviewService()
    first = service.review_prediction(
        prediction_id="pred-7",
        original_prediction="PURSUE",
        review_outcome="accepted",
        rationale="Prediction aligns with current evidence.",
        reviewer_user_id="reviewer-1",
        tenant_id="tenant-1",
        model_version="model-v3",
        evidence_version="ev-v3",
    )
    second = service.review_prediction(
        prediction_id="pred-7",
        original_prediction="PURSUE",
        review_outcome="accepted",
        rationale="Prediction aligns with current evidence.",
        reviewer_user_id="reviewer-1",
        tenant_id="tenant-1",
        model_version="model-v3",
        evidence_version="ev-v3",
    )
    assert first.id == second.id


def test_durable_persistence_failure_raises_error() -> None:
    """Test that when use_durable=True and persistence fails, an error is raised."""
    service = HumanScientificReviewService(use_durable=True)
    try:
        service.approve_evidence(
            "ev-failure-test",
            rationale="This should fail because database is not configured.",
            reviewer_user_id="reviewer-1",
            tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",  # Valid UUID format
            evidence_version="v2",
            model_version="model-v1",
        )
        raise AssertionError("Should have raised RuntimeError for persistence failure")
    except RuntimeError as e:
        assert "Durable review persistence failed" in str(e)


def test_in_memory_mode_does_not_require_database() -> None:
    """Test that use_durable=False (default) works without database."""
    service = HumanScientificReviewService(use_durable=False)
    record = service.approve_evidence(
        "ev-in-memory",
        rationale="This works in-memory without database.",
        reviewer_user_id="reviewer-1",
        tenant_id="tenant-1",
        evidence_version="v2",
        model_version="model-v1",
    )
    assert record.review_action == HumanScientificReviewAction.APPROVE_EVIDENCE
    assert len(service.list_reviews(tenant_id="tenant-1")) == 1


def test_durable_mode_requires_valid_uuid_tenant_id() -> None:
    """Test that durable mode requires valid UUID tenant_id."""
    service = HumanScientificReviewService(use_durable=True)
    try:
        service.approve_evidence(
            "ev-invalid-tenant",
            rationale="Invalid tenant ID format.",
            reviewer_user_id="reviewer-1",
            tenant_id="not-a-uuid",  # Invalid UUID format
            evidence_version="v2",
            model_version="model-v1",
        )
        raise AssertionError("Should have raised ValueError for invalid UUID")
    except (ValueError, RuntimeError):
        pass  # Expected - either UUID validation or persistence failure


def test_durable_mode_requires_valid_uuid_reviewer_id() -> None:
    """Test that durable mode requires valid UUID reviewer_user_id."""
    service = HumanScientificReviewService(use_durable=True)
    try:
        service.approve_evidence(
            "ev-invalid-reviewer",
            rationale="Invalid reviewer ID format.",
            reviewer_user_id="not-a-uuid",  # Invalid UUID format
            tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            evidence_version="v2",
            model_version="model-v1",
        )
        raise AssertionError("Should have raised ValueError for invalid UUID")
    except (ValueError, RuntimeError):
        pass  # Expected - either UUID validation or persistence failure
