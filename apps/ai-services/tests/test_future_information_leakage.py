from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.temporal import (
    InformationLeakageDetector,
    InformationLeakageError,
    LeakageViolationType,
    OutcomeAvailability,
    OutcomeType,
    TemporalIntelligenceEngine,
)


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Publication Leakage Test
# ==============================================================================

def test_intentional_publication_leakage():
    """
    Intentionally attempts to leak a future journal publication into a 2018 historical prediction.
    Model must fail immediately with InformationLeakageError.
    """
    cutoff = date(2018, 1, 1)
    future_publication = {
        "id": "leak-pub-001",
        "title": "NEJM Landmark 2019 Trial Results for Tucatinib",
        "publication_date": "2019-11-20",  # 688 days in the future
        "source_type": "literature",
    }

    # Direct detector audit
    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[future_publication],
            suppressed_items=[],
            strict=True,
        )
    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_publication" in str(exc_info.value)

    # Historical model engine verification
    engine = TemporalIntelligenceEngine()
    with pytest.raises(InformationLeakageError):
        # Attempting to force future publication directly into eligible evidence
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[future_publication],
            suppressed_items=[],
            strict=True,
        )


# ==============================================================================
# 2. Clinical-Result Leakage Test
# ==============================================================================

def test_intentional_clinical_result_leakage():
    """
    Intentionally attempts to leak future clinical trial readouts/endpoints into past predictions.
    Model must fail immediately with InformationLeakageError.
    """
    cutoff = date(2018, 1, 1)
    future_clinical_result = {
        "id": "leak-trial-002",
        "title": "HER2CLIMB Phase 2 Pivotal Endpoint Confirmed",
        "clinical_result_date": "2019-10-01",  # 21 months post-cutoff
        "source_type": "clinical_trial",
    }

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[future_clinical_result],
            suppressed_items=[],
            strict=True,
        )
    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_clinical_result" in str(exc_info.value)


# ==============================================================================
# 3. Approval Leakage Test
# ==============================================================================

def test_intentional_approval_leakage():
    """
    Intentionally attempts to leak a future FDA approval into historical prediction.
    Model must fail immediately with InformationLeakageError.
    """
    cutoff = date(2018, 1, 1)
    future_approval = {
        "id": "leak-appr-003",
        "title": "FDA Grants Regular Approval for Tucatinib (Tukysa)",
        "approval_date": "2020-04-17",  # Over 2 years post-cutoff
        "source_type": "regulatory",
    }

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[future_approval],
            suppressed_items=[],
            strict=True,
        )
    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_approval" in str(exc_info.value)


# ==============================================================================
# 4. Failure Leakage Test
# ==============================================================================

def test_intentional_failure_leakage():
    """
    Intentionally attempts to leak future trial failures / CRL into pre-readout predictions.
    Model must fail immediately with InformationLeakageError.
    """
    cutoff = date(2021, 1, 1)
    future_failure = {
        "id": "leak-fail-004",
        "title": "FDA Issues Complete Response Letter (CRL) Rejecting NDA",
        "failure_date": "2022-11-25",  # Almost 2 years post-cutoff
        "source_type": "regulatory_action",
    }

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[future_failure],
            suppressed_items=[],
            strict=True,
        )
    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_failure" in str(exc_info.value)


# ==============================================================================
# 5. Licensing Leakage Test
# ==============================================================================

def test_intentional_licensing_leakage():
    """
    Intentionally attempts to leak future licensing deals into historical evaluation.
    Model must fail immediately with InformationLeakageError.
    """
    cutoff = date(2020, 1, 1)
    future_licensing = {
        "id": "leak-lic-005",
        "title": "Exclusive Global In-Licensing and Option Agreement Executed",
        "licensing_date": "2022-12-01",  # ~3 years post-cutoff
        "deal_value_usd": 150000000,
    }

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[future_licensing],
            suppressed_items=[],
            strict=True,
        )
    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_licensing_deal" in str(exc_info.value)


# ==============================================================================
# 6. Patent Leakage Test
# ==============================================================================

def test_intentional_patent_leakage():
    """
    Intentionally attempts to leak future patent grants or filings into historical IP assessment.
    Model must fail immediately with InformationLeakageError.
    """
    cutoff = date(2020, 1, 1)
    future_patent = {
        "id": "leak-pat-006",
        "title": "US Patent Granted: Crystalline Form and Stereoselective Synthesis",
        "patent_grant_date": "2022-09-15",  # Over 2.5 years post-cutoff
        "patent_number": "US11440902B2",
    }

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[future_patent],
            suppressed_items=[],
            strict=True,
        )
    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_patent_event" in str(exc_info.value)


# ==============================================================================
# 7. Company-Event Leakage Test
# ==============================================================================

def test_intentional_company_event_leakage():
    """
    Intentionally attempts to leak future corporate buyouts / M&A into historical models.
    Model must fail immediately with InformationLeakageError.
    """
    cutoff = date(2021, 1, 1)
    future_acquisition = {
        "id": "leak-mna-007",
        "title": "Pfizer Completes $43 Billion Acquisition of Seagen Inc.",
        "company_event_date": "2023-12-14",  # Almost 3 years post-cutoff
        "transaction_type": "acquisition",
    }

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[future_acquisition],
            suppressed_items=[],
            strict=True,
        )
    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_company_event" in str(exc_info.value)


# ==============================================================================
# 8. Training Feature & Model Input Leakage Test
# ==============================================================================

def test_historical_models_fail_if_future_information_enters_training_or_prediction_features():
    """
    Verifies that historical models fail immediately if future information enters
    training samples or prediction input features.
    """
    engine = TemporalIntelligenceEngine()
    cutoff = date(2018, 1, 1)

    # Corrupted features with future timestamp
    corrupted_features = {
        "biomarker_concordance": 0.94,
        "preclinical_selectivity_fold": 50,
        "future_pivotal_trial_data": {
            "trial_readout_status": "POSITIVE",
            "date": "2019-11-20",  # Post-cutoff feature!
        },
    }

    with pytest.raises(InformationLeakageError) as exc_info:
        engine.evaluate_historical_prediction(
            asset_id="tucatinib",
            prediction_cutoff=cutoff,
            evidence_cutoff=cutoff,
            input_features=corrupted_features,
            strict_audit=True,
        )

    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_feature_input" in str(exc_info.value)
    assert "Historical models must fail the test" in str(exc_info.value)


# ==============================================================================
# 9. Injected Evidence Leakage Test Through Engine
# ==============================================================================

def test_engine_fails_when_injected_future_evidence_bypasses_sanitization():
    """
    Tests engine pipeline failure when adversarial future evidence is injected
    and directly audited against cutoff.
    """
    engine = TemporalIntelligenceEngine()
    cutoff = date(2018, 1, 1)

    adversarial_leakage_item = {
        "id": "adversarial-leak-item",
        "title": "Adversarial Future Clinical Result Injected",
        "clinical_result_date": "2020-05-10",
        "as_of_date": "2020-05-10",
    }

    # If the item enters the eligible items of audit_items, it must fail
    with pytest.raises(InformationLeakageError):
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=[adversarial_leakage_item],
            suppressed_items=[],
            strict=True,
        )


# ==============================================================================
# 10. REST API Rejection of Adversarial Leakage
# ==============================================================================

def test_api_rejects_adversarial_evidence_leakage(test_client):
    """
    Verifies API rejects future evidence cutoff attempts with 400 status.
    """
    resp = test_client.post(
        "/api/v1/decision/historical/evaluate",
        json={
            "asset_id": "poziotinib",
            "prediction_cutoff": "2021-01-01",
            "evidence_cutoff": "2023-01-01",  # Attempt to leak 2022 CRL into 2021
            "strict_audit": True,
        },
    )
    assert resp.status_code == 400
    assert "Temporal Leakage Violation" in resp.json()["detail"]
