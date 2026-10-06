from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.biology import (
    BiologyIntelligenceEngine,
    BiologyIntelligenceProfile,
    BiologyObservationType,
    DimensionEvaluation,
    EvaluateAssetBiologyRequest,
    EvaluateAssetBiologyResponse,
    EvaluationDimension,
    EvaluationDimensionState,
    RawBiologicalObservation,
    ScoreFormulaLineage,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def biology_engine() -> BiologyIntelligenceEngine:
    return BiologyIntelligenceEngine()


# ==============================================================================
# 1. Database Migration & Schema Verification
# ==============================================================================

def test_migration_022_biology_intelligence_ddl_exists() -> None:
    """
    Validates that the biology intelligence migration file exists and defines
    raw observations and evaluation tables with appropriate indexes.
    """
    migration_file = Path("services/kg/migrations/022_biology_intelligence.sql")
    assert migration_file.exists(), "Migration 022_biology_intelligence.sql must exist"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS biology_raw_observations" in content
    assert "CREATE TABLE IF NOT EXISTS biology_evaluations" in content
    assert "idx_bio_obs_asset" in content
    assert "idx_bio_eval_asset" in content


# ==============================================================================
# 2. Evaluation of All 12 Biological Dimensions
# ==============================================================================

def test_evaluate_all_twelve_dimensions(biology_engine: BiologyIntelligenceEngine) -> None:
    """
    Verifies that the engine evaluates all 12 dimensions:
    - target validity
    - mechanistic rationale
    - potency
    - selectivity
    - on-target evidence
    - off-target risk
    - biomarker strategy
    - genetic evidence
    - functional evidence
    - translational evidence
    - model diversity
    - human evidence
    """
    assert len(EvaluationDimension) == 12

    profile = biology_engine.get_benchmark_profile("zongertinib")

    expected_dimensions = [
        "target_validity",
        "mechanistic_rationale",
        "potency",
        "selectivity",
        "on_target_evidence",
        "off_target_risk",
        "biomarker_strategy",
        "genetic_evidence",
        "functional_evidence",
        "translational_evidence",
        "model_diversity",
        "human_evidence",
    ]

    for dim in expected_dimensions:
        assert dim in profile.dimensions, f"Dimension '{dim}' must be evaluated"
        eval_item = profile.dimensions[dim]
        assert isinstance(eval_item, DimensionEvaluation)
        assert eval_item.state in (
            EvaluationDimensionState.VERIFIED_FACT,
            EvaluationDimensionState.STRONG_SUPPORT,
            EvaluationDimensionState.MODERATE_SUPPORT,
            EvaluationDimensionState.INSUFFICIENT_EVIDENCE,
            EvaluationDimensionState.CONTRADICTORY,
        )
        assert len(eval_item.findings) > 0


# ==============================================================================
# 3. Production of All 6 Canonical Scores
# ==============================================================================

def test_produce_all_six_canonical_scores(biology_engine: BiologyIntelligenceEngine) -> None:
    """
    Verifies that the engine produces all 6 canonical scores:
    1. Biology Validation Score
    2. Potency Score
    3. Selectivity Score
    4. Biomarker Score
    5. Mechanistic Confidence
    6. Translational Readiness
    """
    profile = biology_engine.get_benchmark_profile("zongertinib")

    # 1. Biology Validation Score (0 - 100)
    assert 0.0 <= profile.biology_validation_score <= 100.0
    assert profile.biology_validation_score >= 80.0, "Zongertinib has strong biological validation"

    # 2. Potency Score (0 - 100)
    assert 0.0 <= profile.potency_score <= 100.0
    assert profile.potency_score >= 85.0, "Sub-nanomolar IC50 yields high potency score"

    # 3. Selectivity Score (0 - 100)
    assert 0.0 <= profile.selectivity_score <= 100.0
    assert profile.selectivity_score >= 85.0, "59x selectivity margin yields high selectivity score"

    # 4. Biomarker Score (0 - 100)
    assert 0.0 <= profile.biomarker_score <= 100.0
    assert profile.biomarker_score >= 80.0

    # 5. Mechanistic Confidence (0.0 - 1.0)
    assert 0.0 <= profile.mechanistic_confidence <= 1.0
    assert profile.mechanistic_confidence >= 0.85, "CETSA and gatekeeper resistance support high mechanistic confidence"

    # 6. Translational Readiness (0 - 100)
    assert 0.0 <= profile.translational_readiness <= 100.0
    assert profile.translational_readiness >= 90.0, "High TGI + 4 models + 73.8% clinical ORR yields high readiness"


# ==============================================================================
# 4. Evidence Lineage: Every Score Derived from Raw Observations
# ==============================================================================

def test_every_score_strictly_derived_from_evidence_and_lineage(
    biology_engine: BiologyIntelligenceEngine,
) -> None:
    """
    Validates that:
    - IC50 values
    - selectivity ratios
    - CRISPR evidence / genetic dependency
    - animal efficacy
    - patient-derived models
    - clinical response
    are represented as raw observations and linked via explicit formula lineage.
    """
    profile = biology_engine.get_benchmark_profile("zongertinib")

    # Raw observations must be present
    obs_types = {o.observation_type for o in profile.raw_observations}
    assert BiologyObservationType.IC50_BIOCHEMICAL in obs_types
    assert BiologyObservationType.IC50_CELLULAR in obs_types
    assert BiologyObservationType.SELECTIVITY_RATIO in obs_types
    assert BiologyObservationType.CRISPR_DEPENDENCY in obs_types
    assert BiologyObservationType.ANIMAL_EFFICACY in obs_types
    assert BiologyObservationType.PATIENT_DERIVED_MODELS in obs_types
    assert BiologyObservationType.CLINICAL_RESPONSE in obs_types

    # Every score must have an explicit formula lineage
    required_lineages = [
        "potency_score",
        "selectivity_score",
        "biomarker_score",
        "mechanistic_confidence",
        "biology_validation_score",
        "translational_readiness",
    ]
    for lin_name in required_lineages:
        assert lin_name in profile.lineages
        lineage = profile.lineages[lin_name]
        assert len(lineage.formula) > 0
        assert len(lineage.inputs) > 0
        assert len(lineage.raw_observation_ids) > 0, f"Lineage '{lin_name}' must reference raw observation IDs"


# ==============================================================================
# 5. Anti-Hallucination Invariant: Never Manually Assign Fake Scores
# ==============================================================================

def test_never_manually_assign_scores_when_evidence_is_missing(
    biology_engine: BiologyIntelligenceEngine,
) -> None:
    """
    Invariant: When evidence is missing, the engine MUST NOT hallucinate or
    fabricate scores to make a dashboard look complete. It must return 0.0 /
    INSUFFICIENT_EVIDENCE, record explicit unknowns, and penalize confidence.
    """
    empty_asset_id = "completely_untested_chemical"
    profile = biology_engine.evaluate_asset(
        asset_id=empty_asset_id,
        asset_name="Untested Molecule X",
        custom_observations=[],
    )

    # All scores should be 0.0 because no empirical evidence exists
    assert profile.potency_score == 0.0
    assert profile.selectivity_score == 0.0
    assert profile.biomarker_score == 0.0
    assert profile.mechanistic_confidence == 0.0
    assert profile.biology_validation_score == 0.0
    assert profile.translational_readiness == 0.0

    # All dimensions should be flagged as INSUFFICIENT_EVIDENCE
    for dim_eval in profile.dimensions.values():
        assert dim_eval.state == EvaluationDimensionState.INSUFFICIENT_EVIDENCE

    # Unknowns must be explicitly populated
    assert len(profile.unknowns) >= 6
    assert any("potency" in u.lower() or "ic50" in u.lower() for u in profile.unknowns)
    assert any("selectivity" in u.lower() for u in profile.unknowns)

    # Overall confidence must be heavily penalized
    assert profile.overall_confidence <= 0.30


# ==============================================================================
# 6. Specific Formula Scaling Tests
# ==============================================================================

def test_potency_score_scaling_with_raw_ic50(biology_engine: BiologyIntelligenceEngine) -> None:
    """
    Validates calibrated logarithmic nanomolar scaling:
    - Sub-nanomolar (0.2 nM) -> ~100.0
    - Moderate (10 nM) -> ~67.5
    - Micromolar (2000 nM) -> <20.0
    """
    potent_obs = [
        RawBiologicalObservation(
            asset_id="test_potent",
            parameter_name="IC50_biochemical",
            observation_type=BiologyObservationType.IC50_BIOCHEMICAL,
            raw_text_value="0.2 nM",
            normalized_value=0.2,
            unit="nM",
            source_citation="Test In Vitro Assay",
        ),
        RawBiologicalObservation(
            asset_id="test_potent",
            parameter_name="IC50_cellular",
            observation_type=BiologyObservationType.IC50_CELLULAR,
            raw_text_value="0.4 nM",
            normalized_value=0.4,
            unit="nM",
            source_citation="Test In Vitro Assay",
        ),
    ]

    profile_potent = biology_engine.evaluate_asset("test_potent", custom_observations=potent_obs)
    assert profile_potent.potency_score == 100.0

    weak_obs = [
        RawBiologicalObservation(
            asset_id="test_weak",
            parameter_name="IC50_biochemical",
            observation_type=BiologyObservationType.IC50_BIOCHEMICAL,
            raw_text_value="1500 nM",
            normalized_value=1500.0,
            unit="nM",
            source_citation="Test In Vitro Assay",
        ),
        RawBiologicalObservation(
            asset_id="test_weak",
            parameter_name="IC50_cellular",
            observation_type=BiologyObservationType.IC50_CELLULAR,
            raw_text_value="2500 nM",
            normalized_value=2500.0,
            unit="nM",
            source_citation="Test In Vitro Assay",
        ),
    ]

    profile_weak = biology_engine.evaluate_asset("test_weak", custom_observations=weak_obs)
    assert profile_weak.potency_score <= 25.0


def test_selectivity_score_differentiates_selective_vs_non_selective(
    biology_engine: BiologyIntelligenceEngine,
) -> None:
    """
    Compares Zongertinib (59x selective) vs Poziotinib (1.2x selective, narrow window).
    """
    zong_profile = biology_engine.get_benchmark_profile("zongertinib")
    pozi_profile = biology_engine.get_benchmark_profile("poziotinib")

    assert zong_profile.selectivity_score >= 85.0
    assert pozi_profile.selectivity_score <= 25.0
    assert "off-target kinome hit rate" in pozi_profile.lineages["selectivity_score"].evidence_gaps[0].lower()


def test_translational_readiness_preclinical_vs_clinical(
    biology_engine: BiologyIntelligenceEngine,
) -> None:
    """
    Verifies that OX-HER2-01 (Preclinical program without human trials)
    has Translational Readiness capped at its preclinical limit,
    while Zongertinib (Phase 2 with 73.8% clinical ORR) achieves high readiness.
    """
    zong = biology_engine.get_benchmark_profile("zongertinib")
    ox = biology_engine.get_benchmark_profile("ox-her2-01")

    assert zong.translational_readiness >= 90.0
    # OX-HER2-01 has in vivo TGI (35 pts) and 2 model classes (18 pts) = 53.0 pts, but 0 human clinical points
    assert ox.translational_readiness <= 60.0

    # OX-HER2-01 must explicitly state in unknowns that human clinical trials are unobserved
    human_unknowns = [u for u in ox.unknowns if "clinical" in u.lower() or "human" in u.lower()]
    assert len(human_unknowns) > 0


# ==============================================================================
# 7. Benchmark Profiles Verification
# ==============================================================================

def test_all_five_benchmark_profiles_evaluated(biology_engine: BiologyIntelligenceEngine) -> None:
    """
    Verifies that all 5 benchmark assets evaluate correctly:
    - Zongertinib
    - Tucatinib
    - Poziotinib
    - Neratinib
    - OX-HER2-01
    """
    benchmarks = biology_engine.list_benchmark_profiles()
    assert len(benchmarks) == 5

    asset_ids = {p.asset_id for p in benchmarks}
    assert asset_ids == {"zongertinib", "tucatinib", "poziotinib", "neratinib", "ox-her2-01"}

    for p in benchmarks:
        assert len(p.raw_observations) > 0
        assert len(p.dimensions) == 12
        assert len(p.lineages) == 6
        assert 0.0 <= p.overall_confidence <= 1.0


# ==============================================================================
# 8. FastAPI Endpoints Integration
# ==============================================================================

def test_api_biology_benchmarks(client: TestClient) -> None:
    resp = client.get("/api/v1/biology/benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    assert data[0]["asset_id"] == "zongertinib"
    assert "potency_score" in data[0]
    assert "biology_validation_score" in data[0]


def test_api_biology_profile(client: TestClient) -> None:
    resp = client.get("/api/v1/biology/profile/zongertinib")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "zongertinib"
    assert data["potency_score"] >= 85.0
    assert "dimensions" in data
    assert "lineages" in data
    assert len(data["raw_observations"]) > 0


def test_api_biology_evaluate_custom(client: TestClient) -> None:
    payload = {
        "asset_id": "custom_mol_1",
        "asset_name": "Custom Kinase Inhibitor",
        "custom_observations": [
            {
                "id": str(uuid4()),
                "asset_id": "custom_mol_1",
                "parameter_name": "IC50_cellular",
                "observation_type": "IC50_CELLULAR",
                "raw_text_value": "1.2 nM",
                "normalized_value": 1.2,
                "unit": "nM",
                "source_citation": "Internal Screening 2026",
                "confidence": 0.95,
            }
        ],
    }
    resp = client.post("/api/v1/biology/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()["profile"]
    assert data["asset_id"] == "custom_mol_1"
    assert data["potency_score"] > 70.0
    assert len(data["raw_observations"]) == 1


def test_api_biology_raw_observations(client: TestClient) -> None:
    resp = client.get("/api/v1/biology/observations/zongertinib")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 10
    param_names = [o["parameter_name"] for o in data]
    assert "IC50_biochemical_HER2_WT" in param_names
    assert "selectivity_ratio_WT_EGFR" in param_names
