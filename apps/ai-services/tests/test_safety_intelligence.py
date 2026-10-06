from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.opportunity_engine.safety import (
    AdverseEventRecord,
    AnimalToxicityEvaluation,
    DiscontinuationEvaluation,
    DoseExposureRelationshipEvaluation,
    DoseLimitingToxicityEvaluation,
    EvaluateSafetyRequest,
    MajorRiskSignal,
    OffTargetToxicityEvaluation,
    OrganSystem,
    OrganToxicityProfile,
    RiskSignalSeverity,
    SafetyIntelligenceEngine,
    SafetyIntelligenceProfile,
    SafetyRating,
    TargetRelatedToxicityEvaluation,
    TherapeuticWindowEvaluation,
    ToxicitySeverityGrade,
    SAFETY_INTELLIGENCE_DISCLAIMER,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def safety_engine() -> SafetyIntelligenceEngine:
    return SafetyIntelligenceEngine()


# ==============================================================================
# 1. Database Migration & Schema Verification
# ==============================================================================

def test_migration_028_safety_intelligence_ddl_exists() -> None:
    """
    Validates that the safety intelligence migration file exists and defines
    safety intelligence profiles and adverse event tables with required indexes.
    """
    migration_file = Path("services/kg/migrations/028_safety_intelligence.sql")
    assert migration_file.exists(), "Migration 028_safety_intelligence.sql must exist"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS safety_intelligence_profiles" in content
    assert "CREATE TABLE IF NOT EXISTS safety_adverse_events" in content
    assert "idx_safety_intel_asset" in content
    assert "idx_safety_intel_rating" in content
    assert "idx_safety_intel_score" in content
    assert "idx_safety_ae_asset" in content
    assert "idx_safety_ae_soc" in content


# ==============================================================================
# 2. Capture of All 10 Required Safety & Toxicity Dimensions
# ==============================================================================

def test_capture_all_ten_safety_dimensions(
    safety_engine: SafetyIntelligenceEngine,
) -> None:
    """
    Verifies that safety intelligence profiles capture all 10 required dimensions:
    1. common adverse events
    2. Grade >=3 adverse events
    3. dose-limiting toxicity
    4. discontinuation
    5. organ toxicity
    6. target-related toxicity
    7. off-target toxicity
    8. animal toxicity
    9. therapeutic window
    10. dose exposure relationship
    """
    profile = safety_engine.get_asset_safety_profile("zongertinib")

    # 1. common adverse events
    assert len(profile.common_adverse_events) > 0
    common_ae = profile.common_adverse_events[0]
    assert common_ae.term is not None
    assert common_ae.system_organ_class in OrganSystem
    assert common_ae.any_grade_rate_pct >= 0.0

    # 2. Grade >=3 adverse events
    assert len(profile.grade_3_plus_adverse_events) > 0
    gr3_ae = profile.grade_3_plus_adverse_events[0]
    assert gr3_ae.grade_3_plus_rate_pct >= 0.0

    # 3. dose-limiting toxicity
    assert profile.dose_limiting_toxicity is not None
    assert profile.dose_limiting_toxicity.project_optimus_compliant is True
    assert profile.dose_limiting_toxicity.recommended_phase_2_dose is not None

    # 4. discontinuation
    assert profile.discontinuation is not None
    assert profile.discontinuation.ae_related_discontinuation_pct >= 0.0
    assert profile.discontinuation.dose_reduction_pct >= 0.0

    # 5. organ toxicity
    assert len(profile.organ_toxicities) > 0
    organ = profile.organ_toxicities[0]
    assert organ.organ_system in OrganSystem
    assert len(organ.monitoring_requirement) > 0

    # 6. target-related toxicity
    assert profile.target_related_toxicity is not None
    assert profile.target_related_toxicity.selectivity_ratio_vs_offtarget is not None

    # 7. off-target toxicity
    assert profile.off_target_toxicity is not None
    assert 0.0 <= profile.off_target_toxicity.promiscuity_index <= 1.0

    # 8. animal toxicity
    assert profile.animal_toxicity is not None
    assert len(profile.animal_toxicity.species_evaluated) > 0
    assert profile.animal_toxicity.glp_toxicology_completed is True

    # 9. therapeutic window
    assert profile.therapeutic_window is not None
    assert profile.therapeutic_window.therapeutic_window_ratio > 0.0
    assert len(profile.therapeutic_window.window_width) > 0

    # 10. dose exposure relationship
    assert profile.dose_exposure_relationship is not None
    assert len(profile.dose_exposure_relationship.exposure_safety_correlation) > 0


# ==============================================================================
# 3. Production of Four Core Required Outputs
# ==============================================================================

def test_produce_four_required_outputs(
    safety_engine: SafetyIntelligenceEngine,
) -> None:
    """
    Verifies that querying an asset produces:
    - Safety Score (0 - 100)
    - Therapeutic Index Score (0 - 100)
    - Safety Confidence (0.0 - 1.0)
    - Major Risk Signals
    """
    benchmarks = safety_engine.list_benchmark_profiles()
    assert len(benchmarks) >= 5

    for p in benchmarks:
        assert 0.0 <= p.safety_score <= 100.0
        assert 0.0 <= p.therapeutic_index_score <= 100.0
        assert 0.0 <= p.safety_confidence <= 1.0
        assert isinstance(p.major_risk_signals, list)

        for sig in p.major_risk_signals:
            assert len(sig.title) > 0
            assert sig.severity in RiskSignalSeverity
            assert sig.affected_organ in OrganSystem
            assert len(sig.clinical_evidence) > 0
            assert len(sig.management_recommendation) > 0


# ==============================================================================
# 4. Strict Safety Ratings (GOOD, MODERATE, HIGH RISK, INSUFFICIENT EVIDENCE)
# ==============================================================================

def test_safety_ratings_use_allowed_four_tiers(
    safety_engine: SafetyIntelligenceEngine,
) -> None:
    """
    Verifies that all ratings strictly use one of:
    GOOD, MODERATE, HIGH RISK, INSUFFICIENT EVIDENCE.
    """
    benchmarks = safety_engine.list_benchmark_profiles()
    ratings_found = {p.safety_rating.value for p in benchmarks}

    allowed_ratings = {"GOOD", "MODERATE", "HIGH RISK"}
    assert ratings_found.issubset(allowed_ratings)

    # Fallback asset should produce INSUFFICIENT EVIDENCE
    fallback = safety_engine.get_asset_safety_profile("novel-uncharacterized-x")
    assert fallback.safety_rating == SafetyRating.INSUFFICIENT_EVIDENCE
    assert fallback.safety_rating.value == "INSUFFICIENT EVIDENCE"


# ==============================================================================
# 5. Strict Epistemic Invariant: Missing Evidence Must Not Yield Positive Score
# ==============================================================================

def test_strict_invariant_do_not_convert_missing_safety_evidence_into_positive_score(
    safety_engine: SafetyIntelligenceEngine,
) -> None:
    """
    Strict Invariant:
    Do not convert missing safety evidence into a positive score.
    Assets with missing evidence must be classified as INSUFFICIENT EVIDENCE,
    and cannot receive a safety score > 50.0 or a GOOD rating.
    """
    fallback = safety_engine.get_asset_safety_profile("unknown-molecule-99")

    assert fallback.has_missing_evidence is True
    assert fallback.safety_rating == SafetyRating.INSUFFICIENT_EVIDENCE
    assert fallback.safety_score <= 50.0
    assert fallback.safety_confidence < 0.50
    assert len(fallback.missing_evidence_details) > 0
    assert SAFETY_INTELLIGENCE_DISCLAIMER in fallback.disclaimer


def test_validation_error_when_converting_missing_evidence_to_positive_score() -> None:
    """
    Verifies that attempting to set has_missing_evidence=True with GOOD rating
    or safety_score > 50.0 raises a ValidationError.
    """
    # 1. Missing evidence with rating GOOD must fail
    with pytest.raises(ValidationError) as exc1:
        SafetyIntelligenceProfile(
            asset_id="test1",
            asset_name="Test 1",
            safety_rating=SafetyRating.GOOD,  # VIOLATION
            safety_score=45.0,
            therapeutic_index_score=40.0,
            safety_confidence=0.3,
            has_missing_evidence=True,
            missing_evidence_details=["No GLP tox"],
            dose_limiting_toxicity=DoseLimitingToxicityEvaluation(
                dlt_observed=False,
                project_optimus_compliant=False,
                summary="None",
            ),
            discontinuation=DiscontinuationEvaluation(
                all_cause_discontinuation_pct=0.0,
                ae_related_discontinuation_pct=0.0,
                dose_reduction_pct=0.0,
                dose_interruption_pct=0.0,
                tolerability_impact_summary="None",
            ),
            target_related_toxicity=TargetRelatedToxicityEvaluation(
                target_mechanism="Target",
                is_on_target_liability=False,
                selectivity_protective_effect="None",
                on_target_mitigation="None",
            ),
            off_target_toxicity=OffTargetToxicityEvaluation(
                promiscuity_index=0.2,
                cyp_inhibition_profile="None",
                off_target_risk_summary="None",
            ),
            animal_toxicity=AnimalToxicityEvaluation(
                glp_toxicology_completed=False,
                animal_to_human_translation_note="None",
            ),
            therapeutic_window=TherapeuticWindowEvaluation(
                therapeutic_window_ratio=1.0,
                window_width="None",
                safety_margin_description="None",
            ),
            dose_exposure_relationship=DoseExposureRelationshipEvaluation(
                exposure_safety_correlation="None",
                concentration_dependent_dlt=False,
                pk_variability_impact="None",
            ),
        )
    assert "Epistemic Invariant Violation" in str(exc1.value)

    # 2. Missing evidence with safety_score > 50.0 must fail
    with pytest.raises(ValidationError) as exc2:
        SafetyIntelligenceProfile(
            asset_id="test2",
            asset_name="Test 2",
            safety_rating=SafetyRating.INSUFFICIENT_EVIDENCE,
            safety_score=85.0,  # VIOLATION (> 50.0)
            therapeutic_index_score=80.0,
            safety_confidence=0.3,
            has_missing_evidence=True,
            missing_evidence_details=["No human data"],
            dose_limiting_toxicity=DoseLimitingToxicityEvaluation(
                dlt_observed=False,
                project_optimus_compliant=False,
                summary="None",
            ),
            discontinuation=DiscontinuationEvaluation(
                all_cause_discontinuation_pct=0.0,
                ae_related_discontinuation_pct=0.0,
                dose_reduction_pct=0.0,
                dose_interruption_pct=0.0,
                tolerability_impact_summary="None",
            ),
            target_related_toxicity=TargetRelatedToxicityEvaluation(
                target_mechanism="Target",
                is_on_target_liability=False,
                selectivity_protective_effect="None",
                on_target_mitigation="None",
            ),
            off_target_toxicity=OffTargetToxicityEvaluation(
                promiscuity_index=0.2,
                cyp_inhibition_profile="None",
                off_target_risk_summary="None",
            ),
            animal_toxicity=AnimalToxicityEvaluation(
                glp_toxicology_completed=False,
                animal_to_human_translation_note="None",
            ),
            therapeutic_window=TherapeuticWindowEvaluation(
                therapeutic_window_ratio=1.0,
                window_width="None",
                safety_margin_description="None",
            ),
            dose_exposure_relationship=DoseExposureRelationshipEvaluation(
                exposure_safety_correlation="None",
                concentration_dependent_dlt=False,
                pk_variability_impact="None",
            ),
        )
    assert "Epistemic Invariant Violation" in str(exc2.value)


# ==============================================================================
# 6. Asset-Specific Intelligence Profiles
# ==============================================================================

def test_zongertinib_safety_profile(
    safety_engine: SafetyIntelligenceEngine,
) -> None:
    """
    Verifies Zongertinib:
    - Rating: GOOD
    - Safety Score: 88.0, Therapeutic Index Score: 90.0
    - >59-fold wt-EGFR sparing prevents severe gut/skin toxicity (<3% Gr3 diarrhea)
    - Low discontinuation (<3%)
    """
    profile = safety_engine.get_asset_safety_profile("zongertinib")
    assert profile.asset_id == "zongertinib"
    assert profile.safety_rating == SafetyRating.GOOD
    assert profile.safety_score >= 85.0
    assert profile.therapeutic_index_score >= 85.0
    assert profile.target_related_toxicity.selectivity_ratio_vs_offtarget >= 50.0
    assert profile.discontinuation.ae_related_discontinuation_pct < 5.0

    # Diarrhea rate check
    diarrhea_ae = next(ae for ae in profile.common_adverse_events if ae.term == "Diarrhea")
    assert diarrhea_ae.grade_3_plus_rate_pct < 5.0


def test_tucatinib_safety_profile(
    safety_engine: SafetyIntelligenceEngine,
) -> None:
    """
    Verifies Tucatinib:
    - Rating: GOOD
    - Safety Score: 82.0, Therapeutic Index: 80.0
    - Major Risk Signals: WARNING on hepatotoxicity (routine 3-week LFTs)
    """
    profile = safety_engine.get_asset_safety_profile("tucatinib")
    assert profile.asset_id == "tucatinib"
    assert profile.safety_rating == SafetyRating.GOOD
    assert profile.safety_score >= 80.0

    hep_signal = next(sig for sig in profile.major_risk_signals if sig.affected_organ == OrganSystem.HEPATIC)
    assert hep_signal.severity == RiskSignalSeverity.WARNING
    assert "every 3 weeks" in hep_signal.management_recommendation.lower()


def test_neratinib_and_poziotinib_high_risk_profiles(
    safety_engine: SafetyIntelligenceEngine,
) -> None:
    """
    Verifies Neratinib and Poziotinib:
    - Both rated HIGH RISK
    - Neratinib: 40% Grade 3 diarrhea in ExteNET without prophylaxis
    - Poziotinib: >60% Grade >=3 AEs, 68% dose modification, FDA Complete Response Letter
    """
    ner = safety_engine.get_asset_safety_profile("neratinib")
    assert ner.safety_rating == SafetyRating.HIGH_RISK
    assert ner.safety_score < 60.0
    diarrhea_ae = next(ae for ae in ner.common_adverse_events if ae.term == "Diarrhea")
    assert diarrhea_ae.grade_3_plus_rate_pct >= 35.0

    poz = safety_engine.get_asset_safety_profile("poziotinib")
    assert poz.safety_rating == SafetyRating.HIGH_RISK
    assert poz.safety_score < 30.0
    assert poz.discontinuation.dose_reduction_pct >= 60.0

    crl_signal = next(sig for sig in poz.major_risk_signals if "CRL" in sig.title or "Complete Response Letter" in sig.title)
    assert crl_signal.severity in {RiskSignalSeverity.BLACK_BOX, RiskSignalSeverity.WARNING}


def test_ox_her2_01_preclinical_cns_safety_profile(
    safety_engine: SafetyIntelligenceEngine,
) -> None:
    """
    Verifies OX-HER2-01:
    - Rating: MODERATE
    - GLP tox completed in rats/dogs (NOAEL 25 mg/kg/day)
    - Confidence: 0.65 (preclinical proof without human clinical trials)
    """
    profile = safety_engine.get_asset_safety_profile("ox-her2-01")
    assert profile.asset_id == "ox-her2-01"
    assert profile.safety_rating == SafetyRating.MODERATE
    assert profile.animal_toxicity.glp_toxicology_completed is True
    assert profile.animal_toxicity.noael_dose is not None
    assert 0.50 <= profile.safety_confidence <= 0.80


# ==============================================================================
# 7. FastAPI Integration Tests
# ==============================================================================

def test_fastapi_safety_benchmarks(client: TestClient) -> None:
    response = client.get("/api/v1/safety/benchmarks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    asset_ids = {d["asset_id"] for d in data}
    assert "zongertinib" in asset_ids
    assert "tucatinib" in asset_ids
    assert "neratinib" in asset_ids
    assert "poziotinib" in asset_ids
    assert "ox-her2-01" in asset_ids


def test_fastapi_safety_asset_profile(client: TestClient) -> None:
    response = client.get("/api/v1/safety/asset/zongertinib")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "zongertinib"
    assert data["safety_rating"] == "GOOD"
    assert data["safety_score"] >= 85.0
    assert SAFETY_INTELLIGENCE_DISCLAIMER in data["disclaimer"]


def test_fastapi_safety_risk_signals(client: TestClient) -> None:
    response = client.get("/api/v1/safety/asset/tucatinib/risk-signals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(sig["affected_organ"] == "HEPATIC" for sig in data)


def test_fastapi_safety_evaluate_endpoint(client: TestClient) -> None:
    payload = {
        "asset_id": "zongertinib",
        "target_indication": "NSCLC",
        "min_confidence": 0.80,
    }
    response = client.post("/api/v1/safety/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "zongertinib"
    assert data["safety_confidence"] >= 0.80


def test_fastapi_safety_missing_evidence_fallback(client: TestClient) -> None:
    response = client.get("/api/v1/safety/asset/novel-candidate-uncharacterized")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "novel-candidate-uncharacterized"
    assert data["safety_rating"] == "INSUFFICIENT EVIDENCE"
    assert data["safety_score"] <= 50.0
    assert data["has_missing_evidence"] is True
    assert len(data["missing_evidence_details"]) > 0
    assert SAFETY_INTELLIGENCE_DISCLAIMER in data["disclaimer"]
