from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.opportunity_engine.domain.canonical_model import (
    DevelopmentStage,
    StrategicAction,
)
from app.opportunity_engine.temporal import (
    EvidenceCutoff,
    HistoricalSnapshot,
    InformationLeakageDetector,
    InformationLeakageError,
    LeakageViolationType,
    OutcomeAvailability,
    OutcomeType,
    PredictionSnapshot,
    TemporalCoordinates,
    TemporalFilter,
    TemporalIntelligenceEngine,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_distinguish_seven_temporal_coordinates() -> None:
    """
    Verifies that the platform strictly distinguishes the 7 temporal coordinates:
    1. Evidence publication date
    2. Evidence observation date
    3. Trial date
    4. Outcome date
    5. Regulatory date
    6. Prediction cutoff date
    7. When an outcome became publicly known
    """
    coords = TemporalCoordinates(
        evidence_publication_date=date(2018, 5, 10),
        evidence_observation_date=date(2017, 11, 15),
        trial_date=date(2017, 12, 1),
        outcome_date=date(2017, 12, 20),
        regulatory_date=date(2018, 8, 1),
        prediction_cutoff_date=date(2018, 1, 1),
        publicly_known_date=date(2018, 3, 1),
    )

    # Cutoff is Jan 1, 2018:
    # Observation, trial, and outcome dates happened before cutoff, BUT
    # public disclosure occurred March 1, 2018, and publication occurred May 10, 2018.
    # Therefore, this item must NOT be visible at cutoff!
    assert coords.is_visible_at_cutoff() is False

    # Conversely, an event publicly disclosed in 2017 is visible
    coords_past = TemporalCoordinates(
        evidence_publication_date=date(2017, 6, 1),
        prediction_cutoff_date=date(2018, 1, 1),
        publicly_known_date=date(2017, 6, 1),
    )
    assert coords_past.is_visible_at_cutoff() is True


def test_leakage_detector_catches_future_publication() -> None:
    """
    Verifies that InformationLeakageDetector immediately detects and rejects
    any publication dated after the cutoff date.
    """
    cutoff = date(2018, 1, 1)
    leaked_items = [
        {
            "id": "leaked-paper-2019",
            "title": "Future Landmark Study in NEJM",
            "publication_date": "2019-03-15",  # 438 days after cutoff!
        }
    ]

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=leaked_items,
            suppressed_items=[],
            strict=True,
        )

    assert "CRITICAL LEAKAGE DETECTED" in str(exc_info.value)
    assert "future_publication" in str(exc_info.value)
    assert "Future Landmark Study in NEJM" in str(exc_info.value)


def test_leakage_detector_catches_future_observation_date() -> None:
    """
    Verifies that InformationLeakageDetector catches observations whose lab/clinical
    recording date is post-cutoff.
    """
    cutoff = date(2018, 1, 1)
    leaked_items = [
        {
            "id": "leaked-obs-2018",
            "entity": "HER2 IC50",
            "observation_date": "2018-06-20",  # Post-cutoff
        }
    ]

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=leaked_items,
            suppressed_items=[],
            strict=True,
        )

    assert "future_observation_date" in str(exc_info.value)


def test_leakage_detector_catches_future_trial_results() -> None:
    """
    Verifies detection of trial results first posted on ClinicalTrials.gov after cutoff.
    """
    cutoff = date(2018, 1, 1)
    leaked_items = [
        {
            "id": "NCT09999999",
            "title": "Phase 3 Pivotal Trial Readout",
            "results_first_posted": "2019-11-20",  # Post-cutoff
        }
    ]

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=leaked_items,
            suppressed_items=[],
            strict=True,
        )

    assert "future_trial_result" in str(exc_info.value)


def test_leakage_detector_catches_future_regulatory_decision() -> None:
    """
    Verifies detection of FDA approval or CRL issued after cutoff.
    """
    cutoff = date(2018, 1, 1)
    leaked_items = [
        {
            "id": "FDA-APPROVAL-2020",
            "title": "FDA Regular Approval Announcement",
            "event_date": "2020-04-17",  # Over 2 years post-cutoff!
        }
    ]

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_items(
            asset_id=uuid4(),
            cutoff_date=cutoff,
            eligible_items=leaked_items,
            suppressed_items=[],
            strict=True,
        )

    assert "future_regulatory_decision" in str(exc_info.value)


def test_leakage_detector_catches_delayed_public_disclosure() -> None:
    """
    Critical temporal edge case:
    The actual event occurred on Dec 20, 2017 (before cutoff Jan 1, 2018),
    but was not publicly disclosed or announced until Jan 15, 2018 (after cutoff).
    The system MUST strictly identify this as information leakage!
    """
    cutoff = date(2018, 1, 1)
    outcome = OutcomeAvailability(
        asset_id=uuid4(),
        outcome_type=OutcomeType.TRIAL_READOUT,
        headline="Confidential Trial Endpoint Readout",
        description="Topline readout achieved in Dec 2017 but embargoed until Jan 15 2018.",
        event_date=date(2017, 12, 20),
        publicly_known_date=date(2018, 1, 15),  # 14 days after cutoff!
        disclosure_source="PR Newswire Post-Market Announcement",
    )

    with pytest.raises(InformationLeakageError) as exc_info:
        InformationLeakageDetector.audit_outcomes(
            outcomes=[outcome],
            cutoff_date=cutoff,
            strict=True,
        )

    assert "CRITICAL LEAKAGE" in str(exc_info.value)
    assert "disclosed on 2018-01-15 cannot be visible at cutoff" in str(exc_info.value)


def test_tucatinib_counterfactual_snapshot_january_2018() -> None:
    """
    Simulates prediction cutoff of January 1, 2018 for Tucatinib:
    Must not expose:
    - later publications (2019 NEJM HER2CLIMB)
    - later trial results (2019 HER2CLIMB readout)
    - later approvals (April 2020 FDA approval)
    - later acquisitions (Seattle Genetics $614M in March 2018, Pfizer $43B in Dec 2023)
    Must evaluate owner at cutoff as Cascadian Therapeutics (not Pfizer!)
    Must evaluate stage at cutoff as Phase II (not Approved!)
    """
    engine = TemporalIntelligenceEngine()
    cutoff = date(2018, 1, 1)

    snapshot = engine.evaluate_historical_prediction("tucatinib", cutoff)

    # 1. State at cutoff checks
    assert snapshot.stage_at_cutoff == DevelopmentStage.PHASE_II
    assert snapshot.owner_at_cutoff == "Cascadian Therapeutics"
    assert "CNS" in snapshot.indication_at_cutoff

    # 2. Prediction checks
    assert snapshot.prediction.predicted_action in (StrategicAction.PARTNER, StrategicAction.PURSUE)
    assert snapshot.prediction.predicted_dps >= 70
    assert snapshot.prediction.anti_leakage_audit_passed is True

    # 3. Suppressed future outcomes checks
    future_headlines = [o.headline for o in snapshot.suppressed_future_outcomes]
    assert any("HER2CLIMB" in h for h in future_headlines)
    assert any("Regular Approval" in h for h in future_headlines)
    assert any("Pfizer" in h for h in future_headlines)
    assert any("Seattle Genetics" in h for h in future_headlines)

    # 4. Known outcomes checks
    known_headlines = [o.headline for o in snapshot.known_outcomes_at_cutoff]
    assert any("ONT-380" in h for h in known_headlines)
    # Ensure neither Pfizer nor 2020 FDA approval are in known outcomes!
    assert not any("Pfizer" in h for h in known_headlines)
    assert not any("Tukysa" in h for h in known_headlines)


def test_poziotinib_counterfactual_snapshot_january_2021() -> None:
    """
    Simulates prediction cutoff of January 1, 2021 for Poziotinib:
    System must predict AVOID before the outcome became known:
    - ODAC 9-4 rejection (Sept 2022) is post-cutoff
    - Complete Response Letter (Nov 2022) is post-cutoff
    Must evaluate stage at cutoff as Phase II (not Terminated!)
    """
    engine = TemporalIntelligenceEngine()
    cutoff = date(2021, 1, 1)

    snapshot = engine.evaluate_historical_prediction("poziotinib", cutoff)

    assert snapshot.stage_at_cutoff == DevelopmentStage.PHASE_II
    assert snapshot.prediction.predicted_action == StrategicAction.AVOID
    assert snapshot.prediction.predicted_dps < 25
    assert "ODAC" in snapshot.ground_truth_post_cutoff_outcome
    assert snapshot.accuracy_assessment == "True Negative"

    # Suppressed future outcomes
    future_headlines = [o.headline for o in snapshot.suppressed_future_outcomes]
    assert any("ODAC" in h for h in future_headlines)
    assert any("Complete Response Letter" in h for h in future_headlines)


def test_neratinib_counterfactual_snapshot_july_2017() -> None:
    """
    Simulates prediction cutoff of July 1, 2017 for Neratinib:
    FDA approval was July 17, 2017.
    At July 1, 2017, the stage was Phase III, NOT Approved!
    System must predict MONITOR / NICHE USE due to diarrhea liabilities.
    """
    engine = TemporalIntelligenceEngine()
    cutoff = date(2017, 7, 1)

    snapshot = engine.evaluate_historical_prediction("neratinib", cutoff)

    assert snapshot.stage_at_cutoff == DevelopmentStage.PHASE_III
    assert snapshot.prediction.predicted_action == StrategicAction.MONITOR
    assert snapshot.accuracy_assessment == "Calibrated Success"

    future_headlines = [o.headline for o in snapshot.suppressed_future_outcomes]
    assert any("FDA Approves Nerlynx" in h for h in future_headlines)


def test_temporal_snapshot_api_endpoint(client: TestClient) -> None:
    """
    Tests REST endpoint GET /api/v1/decision/snapshots/{asset_id}?cutoff_date=YYYY-MM-DD.
    """
    resp = client.get("/api/v1/decision/snapshots/tucatinib?cutoff_date=2018-01-01")
    assert resp.status_code == 200
    data = resp.json()

    assert data["asset_name"] == "Tucatinib"
    assert data["owner_at_cutoff"] == "Cascadian Therapeutics"
    assert data["stage_at_cutoff"] == "Phase II"
    assert data["audit_report"]["audit_passed"] is True
    assert len(data["suppressed_future_outcomes"]) >= 3


def test_migration_015_exists() -> None:
    """Verifies that 015_temporal_intelligence.sql exists and defines all required tables."""
    migration_path = Path("services/kg/migrations/015_temporal_intelligence.sql")
    assert migration_path.exists(), "Migration 015_temporal_intelligence.sql missing"
    content = migration_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS outcome_availabilities" in content
    assert "CREATE TABLE IF NOT EXISTS prediction_snapshots" in content
    assert "CREATE TABLE IF NOT EXISTS historical_snapshots" in content
    assert "CREATE TABLE IF NOT EXISTS temporal_audit_logs" in content
