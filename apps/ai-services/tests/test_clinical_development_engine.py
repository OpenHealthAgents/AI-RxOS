from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.clinical import (
    ClinicalDevelopmentIntelligenceEngine,
    ClinicalDevelopmentProfile,
    ClinicalExpertInterpretation,
    ClinicalModelPrediction,
    ClinicalScoreLineage,
    ClinicalStage,
    EndpointReviewType,
    EpistemicCategory,
    EvaluateAssetClinicalRequest,
    EvaluateAssetClinicalResponse,
    ObservedClinicalOutcome,
    TrialDesignEvaluation,
    TrialDesignType,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def clinical_engine() -> ClinicalDevelopmentIntelligenceEngine:
    return ClinicalDevelopmentIntelligenceEngine()


# ==============================================================================
# 1. Database Migration & Schema Verification
# ==============================================================================

def test_migration_024_clinical_intelligence_ddl_exists() -> None:
    """
    Validates that the clinical intelligence migration file exists and defines
    trial evaluations and intelligence profile tables with indexes.
    """
    migration_file = Path("services/kg/migrations/024_clinical_intelligence.sql")
    assert migration_file.exists(), "Migration 024_clinical_intelligence.sql must exist"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS clinical_trials_evaluations" in content
    assert "CREATE TABLE IF NOT EXISTS clinical_intelligence_evaluations" in content
    assert "idx_clin_trials_asset" in content
    assert "idx_clin_eval_asset" in content


# ==============================================================================
# 2. Evaluation of All 17 Required Clinical Dimensions
# ==============================================================================

def test_evaluate_all_seventeen_clinical_dimensions(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    """
    Verifies evaluation of all 17 dimensions:
    stage, trial design, enrollment, population selection, biomarker enrichment,
    endpoint quality, ORR, CR, DOR, PFS, OS, clinical benefit, toxicity,
    discontinuation, dose optimization, trial execution, competitive clinical landscape.
    """
    profile = clinical_engine.get_benchmark_profile("tucatinib")

    # 1. stage
    assert profile.stage == ClinicalStage.APPROVED

    # 2. trial design, 3. enrollment, 4. population, 5. biomarker, 6. endpoint quality, 15. dose optimization, 16. trial execution
    assert len(profile.trials_evaluated) > 0
    trial = profile.trials_evaluated[0]
    assert trial.design_type == TrialDesignType.RANDOMIZED_CONTROLLED_TRIAL
    assert trial.enrollment_count == 612
    assert trial.comparator_arm is not None
    assert trial.biomarker_prospective is True
    assert trial.adjudication == EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW
    assert trial.project_optimus_compliant is True
    assert len(trial.execution_flags) > 0

    # 7. ORR, 8. CR, 9. DOR, 10. PFS, 11. OS, 12. clinical benefit, 13. toxicity, 14. discontinuation
    assert len(profile.observed_clinical_outcomes) > 0
    outcome = profile.observed_clinical_outcomes[0]
    assert outcome.orr_pct == 40.6
    assert outcome.cr_pct == 1.4
    assert outcome.dor_months == 8.3
    assert outcome.pfs_months == 7.8
    assert outcome.pfs_hazard_ratio == 0.54
    assert outcome.os_months == 21.9
    assert outcome.os_hazard_ratio == 0.66
    assert outcome.cbr_pct == 72.0
    assert outcome.grade_3_plus_ae_pct == 12.9
    assert outcome.treatment_discontinuation_pct == 5.7

    # 17. competitive clinical landscape
    assert len(profile.expert_interpretations) > 0
    assert any("competitive" in exp.topic.lower() for exp in profile.expert_interpretations)


# ==============================================================================
# 3. Production of All 4 Canonical Scores
# ==============================================================================

def test_produce_four_canonical_scores(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    """
    Verifies production of:
    1. Clinical Success Probability (0.0 - 1.0)
    2. Clinical Readiness Score (0 - 100)
    3. Development Risk Score (0 - 100)
    4. Evidence Confidence (0.0 - 1.0)
    """
    profile = clinical_engine.get_benchmark_profile("tucatinib")

    assert 0.0 <= profile.clinical_success_probability <= 1.0
    assert 0.0 <= profile.clinical_readiness_score <= 100.0
    assert 0.0 <= profile.development_risk_score <= 100.0
    assert 0.0 <= profile.evidence_confidence <= 1.0

    # Tucatinib is approved with randomized OS benefit
    assert profile.clinical_success_probability >= 0.95
    assert profile.clinical_readiness_score >= 90.0
    assert profile.development_risk_score <= 35.0
    assert profile.evidence_confidence >= 0.95


# ==============================================================================
# 4. Strict Epistemic Separation
# ==============================================================================

def test_strict_epistemic_separation(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    """
    Verifies strict separation of:
    - observed clinical outcome (facts)
    - model prediction (algorithmic)
    - expert interpretation (clinician/regulatory)
    - unknown (evidence gaps)
    """
    profile = clinical_engine.get_benchmark_profile("zongertinib")

    # 1. Observed clinical outcomes must contain real trial facts
    assert len(profile.observed_clinical_outcomes) > 0
    for obs in profile.observed_clinical_outcomes:
        assert isinstance(obs, ObservedClinicalOutcome)
        assert obs.trial_id == "NCT04886804"
        assert obs.orr_pct == 73.8
        assert len(obs.source_citation) > 0

    # 2. Model predictions must contain statistical projections with model names
    assert len(profile.model_predictions) > 0
    for pred in profile.model_predictions:
        assert isinstance(pred, ClinicalModelPrediction)
        assert len(pred.model_name) > 0
        assert pred.predicted_value > 0

    # 3. Expert interpretations must contain clinical guidance
    assert len(profile.expert_interpretations) > 0
    for exp in profile.expert_interpretations:
        assert isinstance(exp, ClinicalExpertInterpretation)
        assert len(exp.consensus_view) > 0
        assert len(exp.expert_source) > 0

    # 4. Unknowns must explicitly list gaps
    assert len(profile.unknowns) > 0
    for unk in profile.unknowns:
        assert isinstance(unk, str)
        assert len(unk.strip()) > 0


# ==============================================================================
# 5. Benchmark Profiles Validation
# ==============================================================================

def test_tucatinib_phase_3_approved_profile(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    tuc = clinical_engine.get_benchmark_profile("tucatinib")
    assert tuc.stage == ClinicalStage.APPROVED
    assert tuc.clinical_success_probability >= 0.95
    assert tuc.clinical_readiness_score >= 90.0
    assert tuc.development_risk_score <= 35.0
    assert tuc.evidence_confidence >= 0.95


def test_zongertinib_phase_2_mutant_nsclc_profile(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    zong = clinical_engine.get_benchmark_profile("zongertinib")
    assert zong.stage == ClinicalStage.PHASE_II
    assert zong.clinical_success_probability >= 0.65
    assert zong.clinical_readiness_score >= 70.0
    assert zong.development_risk_score <= 45.0
    assert zong.observed_clinical_outcomes[0].orr_pct == 73.8
    assert zong.observed_clinical_outcomes[0].grade_3_plus_ae_pct == 3.8
    # Project optimus randomized dose exploration verified
    assert zong.trials_evaluated[0].project_optimus_compliant is True


def test_poziotinib_crl_high_development_risk(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    poz = clinical_engine.get_benchmark_profile("poziotinib")
    assert poz.stage == ClinicalStage.CRL
    assert poz.clinical_success_probability <= 0.15
    assert poz.development_risk_score >= 80.0  # High development risk due to CRL, 26% diarrhea, 68% dose reduction
    assert poz.observed_clinical_outcomes[0].dose_reduction_pct == 68.0


def test_neratinib_approved_with_high_diarrhea_risk(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    ner = clinical_engine.get_benchmark_profile("neratinib")
    assert ner.stage == ClinicalStage.APPROVED
    assert ner.clinical_readiness_score >= 85.0
    # Development risk is elevated despite approval due to 40% Grade 3 diarrhea
    assert ner.development_risk_score >= 60.0
    assert ner.observed_clinical_outcomes[0].grade_3_plus_ae_pct == 40.0


def test_ox_her2_01_preclinical_profile_zero_clinical_outcomes(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    ox = clinical_engine.get_benchmark_profile("ox-her2-01")
    assert ox.stage == ClinicalStage.PRECLINICAL
    # Invariant: NO clinical outcomes observed!
    assert ox.observed_clinical_outcomes == []
    assert ox.trials_evaluated == []

    # Scores reflect preclinical stage
    assert ox.clinical_success_probability <= 0.20
    assert ox.clinical_readiness_score <= 25.0
    assert ox.development_risk_score >= 70.0
    assert ox.evidence_confidence <= 0.25

    # Unknowns explicitly state absence of clinical trials
    assert any("no human clinical trials" in u.lower() for u in ox.unknowns)


# ==============================================================================
# 6. Lineage and Formula Provenance
# ==============================================================================

def test_show_evidence_behind_every_score_lineage(
    clinical_engine: ClinicalDevelopmentIntelligenceEngine,
) -> None:
    profile = clinical_engine.get_benchmark_profile("tucatinib")

    assert "clinical_success_probability" in profile.lineages
    assert "clinical_readiness_score" in profile.lineages
    assert "development_risk_score" in profile.lineages
    assert "evidence_confidence" in profile.lineages

    for score_name, lin in profile.lineages.items():
        assert len(lin.formula) > 0
        assert len(lin.inputs) > 0
        assert len(lin.observed_outcome_ids) > 0, f"Lineage for '{score_name}' must link to observed outcome IDs"


# ==============================================================================
# 7. FastAPI Endpoints Integration
# ==============================================================================

def test_api_clinical_benchmarks(client: TestClient) -> None:
    resp = client.get("/api/v1/clinical/benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    asset_ids = {p["asset_id"] for p in data}
    assert asset_ids == {"tucatinib", "zongertinib", "poziotinib", "neratinib", "ox-her2-01"}


def test_api_clinical_profile(client: TestClient) -> None:
    resp = client.get("/api/v1/clinical/profile/zongertinib")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "zongertinib"
    assert data["stage"] == "PHASE_II"
    assert data["clinical_success_probability"] >= 0.65
    assert len(data["observed_clinical_outcomes"]) == 1
    assert len(data["model_predictions"]) >= 1
    assert len(data["expert_interpretations"]) >= 1


def test_api_clinical_evaluate_custom(client: TestClient) -> None:
    payload = {
        "asset_id": "custom_asset_1",
        "asset_name": "Custom Clinical Molecule",
        "custom_outcomes": [
            {
                "id": str(uuid4()),
                "trial_id": "NCT99999999",
                "trial_title": "Phase 2 Proof of Concept",
                "phase": "PHASE_II",
                "sample_size": 85,
                "population": "Solid tumor patients",
                "biomarker_status": "Target-mutant positive",
                "orr_pct": 52.0,
                "grade_3_plus_ae_pct": 14.0,
                "source_citation": "Custom Trial Report 2026",
            }
        ],
    }
    resp = client.post("/api/v1/clinical/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()["profile"]
    assert data["asset_id"] == "custom_asset_1"
    assert data["clinical_success_probability"] > 0.20
    assert len(data["observed_clinical_outcomes"]) == 1


def test_api_clinical_observed_outcomes(client: TestClient) -> None:
    resp = client.get("/api/v1/clinical/outcomes/tucatinib")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["trial_id"] == "NCT02614794"
    assert data[0]["orr_pct"] == 40.6
    assert data[0]["os_months"] == 21.9
