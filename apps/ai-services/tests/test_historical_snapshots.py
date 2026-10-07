import pytest
from datetime import date
from uuid import UUID
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.domain.canonical_model import (
    DevelopmentStage,
    StrategicAction,
)
from app.opportunity_engine.temporal import (
    HistoricalSnapshot,
    InformationLeakageError,
    TemporalIntelligenceEngine,
)


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


def test_historical_snapshot_cutoff_coordinates():
    """
    Verifies that HistoricalSnapshot explicitly supports:
    1. prediction_cutoff
    2. evidence_cutoff
    3. outcome_known_at_cutoff
    and captures exactly what was knowable at the cutoff.
    """
    engine = TemporalIntelligenceEngine()

    # 1. Poziotinib as of 2018-01-01: No clinical failures or CRLs were known yet
    snap_early = engine.evaluate_historical_prediction(
        asset_id="poziotinib",
        prediction_cutoff=date(2018, 1, 1),
        evidence_cutoff=date(2018, 1, 1),
    )
    assert snap_early.prediction_cutoff == date(2018, 1, 1)
    assert snap_early.evidence_cutoff == date(2018, 1, 1)
    assert snap_early.outcome_known_at_cutoff is False
    assert len(snap_early.known_outcomes_at_cutoff) == 0
    assert len(snap_early.suppressed_future_outcomes) >= 3
    assert snap_early.stage_at_cutoff == DevelopmentStage.PHASE_II
    assert snap_early.owner_at_cutoff == "Spectrum Pharmaceuticals"
    assert snap_early.prediction.predicted_action == StrategicAction.AVOID

    # 2. Poziotinib as of 2020-01-01: ZENITH20 Cohort 1 failure was known in Dec 2019
    snap_mid = engine.evaluate_historical_prediction(
        asset_id="poziotinib",
        prediction_cutoff=date(2020, 1, 1),
        evidence_cutoff=date(2020, 1, 1),
    )
    assert snap_mid.prediction_cutoff == date(2020, 1, 1)
    assert snap_mid.evidence_cutoff == date(2020, 1, 1)
    assert snap_mid.outcome_known_at_cutoff is True
    assert len(snap_mid.known_outcomes_at_cutoff) == 1
    assert "ZENITH20" in snap_mid.known_outcomes_at_cutoff[0].headline
    # ODAC rejection and CRL from 2022 must remain suppressed!
    assert not any("ODAC" in o.headline for o in snap_mid.known_outcomes_at_cutoff)
    assert not any("Complete Response Letter" in o.headline for o in snap_mid.known_outcomes_at_cutoff)


def test_anti_leakage_prohibits_future_evidence_cutoff():
    """
    Verifies that the platform strictly prevents future information leakage:
    If evidence_cutoff > prediction_cutoff, it must immediately raise InformationLeakageError.
    """
    engine = TemporalIntelligenceEngine()

    with pytest.raises(InformationLeakageError) as exc_info:
        engine.evaluate_historical_prediction(
            asset_id="tucatinib",
            prediction_cutoff=date(2018, 1, 1),
            evidence_cutoff=date(2019, 1, 1),  # Leakage! Future evidence into past prediction
            strict_audit=True,
        )

    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "evidence_cutoff" in str(exc_info.value)
    assert "cannot be later than prediction_cutoff" in str(exc_info.value)


def test_tucatinib_what_was_knowable_at_january_2018_cutoff():
    """
    Simulates prediction cutoff of January 1, 2018 for Tucatinib:
    Must represent exactly what was knowable at that point in time:
    - Owner: Cascadian Therapeutics (NOT Seattle Genetics, NOT Pfizer)
    - Stage: Phase II (NOT Approved)
    - Suppressed outcomes: 2018 buyout, 2019 HER2CLIMB readout, 2020 FDA approval, 2023 Pfizer buyout
    - Prediction: StrategicAction.PARTNER, DPS >= 70
    - outcome_known_at_cutoff: True (ONT-380 Phase 1 CNS response known from Oct 2017)
    """
    engine = TemporalIntelligenceEngine()
    snap = engine.evaluate_historical_prediction(
        asset_id="tucatinib",
        prediction_cutoff=date(2018, 1, 1),
        evidence_cutoff=date(2018, 1, 1),
    )

    assert snap.prediction_cutoff == date(2018, 1, 1)
    assert snap.evidence_cutoff == date(2018, 1, 1)
    assert snap.outcome_known_at_cutoff is True
    assert snap.stage_at_cutoff == DevelopmentStage.PHASE_II
    assert snap.owner_at_cutoff == "Cascadian Therapeutics"
    assert snap.prediction.predicted_action == StrategicAction.PARTNER
    assert snap.prediction.anti_leakage_audit_passed is True

    # Check future suppression
    suppressed_headlines = [o.headline for o in snap.suppressed_future_outcomes]
    assert any("Seattle Genetics" in h for h in suppressed_headlines)
    assert any("HER2CLIMB" in h for h in suppressed_headlines)
    assert any("Regular Approval" in h for h in suppressed_headlines)
    assert any("Pfizer" in h for h in suppressed_headlines)


def test_api_post_historical_evaluate(test_client):
    """
    Verifies POST /api/v1/decision/historical/evaluate returns frozen snapshot.
    """
    payload = {
        "asset_id": "poziotinib",
        "prediction_cutoff": "2021-01-01",
        "evidence_cutoff": "2021-01-01",
        "strict_audit": True,
    }
    resp = test_client.post("/api/v1/decision/historical/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["prediction_cutoff"] == "2021-01-01"
    assert data["evidence_cutoff"] == "2021-01-01"
    assert data["outcome_known_at_cutoff"] is True
    assert data["stage_at_cutoff"] == "Phase II"
    assert data["owner_at_cutoff"] == "Spectrum Pharmaceuticals"
    assert data["prediction"]["predicted_action"] == "AVOID"
    assert data["prediction"]["anti_leakage_audit_passed"] is True
    assert data["audit_report"]["audit_passed"] is True


def test_api_post_historical_evaluate_rejects_leakage(test_client):
    """
    Verifies POST /api/v1/decision/historical/evaluate returns 400 when evidence_cutoff > prediction_cutoff.
    """
    payload = {
        "asset_id": "tucatinib",
        "prediction_cutoff": "2018-01-01",
        "evidence_cutoff": "2020-01-01",  # 2 years in the future!
        "strict_audit": True,
    }
    resp = test_client.post("/api/v1/decision/historical/evaluate", json=payload)
    assert resp.status_code == 400
    assert "Temporal Leakage Violation" in resp.json()["detail"]


def test_api_get_historical_snapshot(test_client):
    """
    Verifies GET /api/v1/decision/historical/snapshots/{asset_id}.
    """
    resp = test_client.get(
        "/api/v1/decision/historical/snapshots/tucatinib?prediction_cutoff=2018-01-01&evidence_cutoff=2018-01-01"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["prediction_cutoff"] == "2018-01-01"
    assert data["evidence_cutoff"] == "2018-01-01"
    assert data["outcome_known_at_cutoff"] is True
    assert data["owner_at_cutoff"] == "Cascadian Therapeutics"


def test_api_post_historical_batch_evaluate(test_client):
    """
    Verifies POST /api/v1/decision/historical/batch-evaluate evaluates multiple assets at cutoff.
    """
    payload = {
        "asset_ids": ["tucatinib", "poziotinib", "neratinib"],
        "prediction_cutoff": "2018-01-01",
        "evidence_cutoff": "2018-01-01",
        "strict_audit": True,
    }
    resp = test_client.post("/api/v1/decision/historical/batch-evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["prediction_cutoff"] == "2018-01-01"
    assert data["evidence_cutoff"] == "2018-01-01"
    assert data["total_evaluated"] == 3
    assert len(data["snapshots"]) == 3

    # Tucatinib is PARTNER, Poziotinib is AVOID, Neratinib is MONITOR
    actions = {s["asset_name"]: s["prediction"]["predicted_action"] for s in data["snapshots"]}
    assert actions["Tucatinib"] == "PARTNER"
    assert actions["Poziotinib"] == "AVOID"
    assert actions["Neratinib"] == "MONITOR"


def test_api_get_historical_timeline(test_client):
    """
    Verifies GET /api/v1/decision/historical/timeline/{asset_id} returns milestones.
    """
    resp = test_client.get("/api/v1/decision/historical/timeline/tucatinib")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "tucatinib"
    assert len(data["milestones"]) >= 3

    m0 = data["milestones"][0]
    assert m0["prediction_cutoff"] == "2017-06-01"
    assert m0["outcome_known_at_cutoff"] is False
    assert m0["owner_at_cutoff"] == "Cascadian Therapeutics"
    assert m0["stage_at_cutoff"] == "Phase I"
