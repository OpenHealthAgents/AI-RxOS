from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.patient_match import (
    AssetPatientMatchProfile,
    BiomarkerStrategy,
    CandidateAssetMatchRank,
    PatientCohortQuery,
    PatientMatchEngine,
    PatientMatchScenarioResponse,
    PopulationRecommendation,
    PopulationTier,
    POPULATION_INTELLIGENCE_DISCLAIMER,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def patient_match_engine() -> PatientMatchEngine:
    return PatientMatchEngine()


# ==============================================================================
# 1. Database Migration & Schema Verification
# ==============================================================================

def test_migration_025_patient_match_ddl_exists() -> None:
    """
    Validates that the PatientMatch intelligence migration file exists and defines
    population profiles and scenario audit tables with indexes.
    """
    migration_file = Path("services/kg/migrations/025_patient_match_intelligence.sql")
    assert migration_file.exists(), "Migration 025_patient_match_intelligence.sql must exist"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS patient_population_profiles" in content
    assert "CREATE TABLE IF NOT EXISTS patient_match_scenario_audits" in content
    assert "idx_patient_pop_asset" in content
    assert "idx_match_audit_time" in content



# ==============================================================================
# 2. Answering: "Which patients are most likely to benefit from this asset?"
# ==============================================================================

def test_asset_patient_match_answers_who_benefits_most(
    patient_match_engine: PatientMatchEngine,
) -> None:
    """
    Verifies that querying an asset answers:
    'Which patients are most likely to benefit from this asset?'
    yielding Best, Secondary, and Excluded populations with scores and confidence.
    """
    profile = patient_match_engine.get_asset_patient_match("zongertinib")

    assert profile.asset_id == "zongertinib"
    assert "Zongertinib" in profile.asset_name
    assert profile.patient_match_score >= 85.0
    assert 0.0 <= profile.confidence <= 1.0

    # Best Patient Population
    assert profile.best_patient_population.tier == PopulationTier.BEST
    assert "HER2" in profile.best_patient_population.biomarker
    assert "HER2 Exon 20 insertion" in profile.best_patient_population.mutation or "L755S" in profile.best_patient_population.mutation
    assert len(profile.best_patient_population.evidence_citations) > 0

    # Secondary Patient Population
    assert profile.secondary_patient_population.tier == PopulationTier.SECONDARY
    assert "Breast Cancer" in profile.secondary_patient_population.disease_subtype or "Solid Tumors" in profile.secondary_patient_population.disease_subtype

    # Excluded Population
    assert profile.excluded_patient_population.tier == PopulationTier.EXCLUDED
    assert "Wild-type" in profile.excluded_patient_population.name or "EGFR" in profile.excluded_patient_population.description

    # Biomarker Strategy
    assert profile.biomarker_strategy.primary_biomarker is not None
    assert "NGS" in profile.biomarker_strategy.assay_modality or "ctDNA" in profile.biomarker_strategy.assay_modality


# ==============================================================================
# 3. Evaluation of All 12 Required Input Dimensions
# ==============================================================================

def test_evaluation_across_all_twelve_dimensions(
    patient_match_engine: PatientMatchEngine,
) -> None:
    """
    Verifies explicit evaluation across all 12 dimensions:
    mutation, expression, amplification, protein expression, biomarker,
    disease subtype, prior therapy, resistance state, line of therapy,
    CNS status, clinical evidence, mechanism.
    """
    benchmarks = patient_match_engine.list_benchmark_profiles()
    assert len(benchmarks) >= 5

    for profile in benchmarks:
        best_pop = profile.best_patient_population

        # 1. mutation
        assert best_pop.mutation is not None
        # 2. expression
        assert best_pop.expression is not None
        # 3. amplification
        assert best_pop.amplification is not None
        # 4. protein expression
        assert best_pop.protein_expression is not None
        # 5. biomarker
        assert best_pop.biomarker is not None and len(best_pop.biomarker) > 0
        # 6. disease subtype
        assert best_pop.disease_subtype is not None and len(best_pop.disease_subtype) > 0
        # 7. prior therapy
        assert isinstance(best_pop.prior_therapy, list)
        # 8. resistance state
        assert best_pop.resistance_state is not None
        # 9. line of therapy
        assert best_pop.line_of_therapy is not None and len(best_pop.line_of_therapy) > 0
        # 10. CNS status
        assert best_pop.cns_status is not None and len(best_pop.cns_status) > 0
        # 11. clinical evidence
        assert len(best_pop.evidence_citations) > 0 or len(best_pop.evidence_summary) > 0
        # 12. mechanism
        assert profile.mechanism is not None and len(profile.mechanism) > 0


# ==============================================================================
# 4. Excluded / Low-Likelihood Populations
# ==============================================================================

def test_excluded_low_likelihood_populations_with_evidence(
    patient_match_engine: PatientMatchEngine,
) -> None:
    """
    Verifies that excluded/low-likelihood populations are clearly identified
    with clinical and mechanistic rationale (toxicity, lack of target, resistance).
    """
    # Tucatinib excludes HER2-negative / non-amplified tumors lacking HER2 overexpression
    tuc = patient_match_engine.get_asset_patient_match("tucatinib")
    assert tuc.excluded_patient_population.tier == PopulationTier.EXCLUDED
    assert "non-amplified" in tuc.excluded_patient_population.name.lower() or "lacking her2 gene amplification" in tuc.excluded_patient_population.description.lower()


    # Poziotinib excludes frail or unselected patients due to non-selective EGFR toxicity
    poz = patient_match_engine.get_asset_patient_match("poziotinib")
    assert poz.excluded_patient_population.tier == PopulationTier.EXCLUDED
    assert "toxicit" in poz.excluded_patient_population.name.lower() or "dose interruptions" in poz.excluded_patient_population.description.lower()


    # Neratinib excludes patients unable to comply with loperamide prophylaxis due to severe diarrhea
    ner = patient_match_engine.get_asset_patient_match("neratinib")
    assert ner.excluded_patient_population.tier == PopulationTier.EXCLUDED
    assert "diarrhea" in ner.excluded_patient_population.description.lower() or "gastrointestinal" in ner.excluded_patient_population.description.lower()


# ==============================================================================
# 5. Biomarker Strategy & Diagnostic Feasibility
# ==============================================================================

def test_biomarker_strategy_and_companion_diagnostics(
    patient_match_engine: PatientMatchEngine,
) -> None:
    """
    Verifies biomarker strategy includes companion diagnostic requirements,
    assay modality, and stratification hypothesis.
    """
    profile = patient_match_engine.get_asset_patient_match("zongertinib")
    strat = profile.biomarker_strategy

    assert "ERBB2" in strat.primary_biomarker or "HER2" in strat.primary_biomarker
    assert "ctDNA" in strat.assay_modality or "NGS" in strat.assay_modality
    assert len(strat.stratification_hypothesis) > 0
    assert "High" in strat.feasibility or "Feasible" in strat.feasibility
    assert len(strat.co_testing_requirements) > 0


# ==============================================================================
# 6. Specific Cohort Scenario: ER+/HER2-mutant mBC post-CDK4/6 progression
# ==============================================================================

def test_er_plus_her2_mutant_post_cdk46_progression_scenario(
    patient_match_engine: PatientMatchEngine,
) -> None:
    """
    Evaluates scenario: 'ER+/HER2-mutant breast cancer after CDK4/6 progression'.
    Verifies that Zongertinib ranks #1 due to mutant selectivity and favorable toxicity,
    fulvestrant is recommended as combination partner, and Neratinib/Tucatinib are ranked.
    """
    query = PatientCohortQuery(
        disease_subtype="HR+/HER2-non-amplified Metastatic Breast Cancer",
        mutation="HER2 L755S / V777L activating kinase domain mutations",
        expression="ER-positive (Allred 8), PR-positive",
        amplification="HER2 non-amplified (FISH ratio 1.2, IHC 1+)",
        protein_expression="HER2 IHC 1+",
        biomarker="ER+/HER2-mutant (non-amplified)",
        prior_therapy=["CDK4/6 inhibitor (palbociclib)", "Letrozole"],
        resistance_state="Acquired endocrine & CDK4/6 resistance via ERBB2 kinase mutation",
        line_of_therapy="2L+ Metastatic",
        cns_status="High risk for CNS progression",
    )

    scenario_res = patient_match_engine.match_cohort_scenario(query)

    assert scenario_res.query.biomarker == "ER+/HER2-mutant (non-amplified)"
    assert scenario_res.best_matched_asset.asset_id == "zongertinib"
    assert scenario_res.best_matched_asset.patient_match_score >= 88.0

    # Verify ranked candidates
    candidate_ids = [c.asset_id for c in scenario_res.ranked_candidates]
    assert candidate_ids[0] == "zongertinib"
    assert "neratinib" in candidate_ids
    assert "tucatinib" in candidate_ids

    # Top candidate should have combination recommendation (e.g. Fulvestrant)
    top_cand = scenario_res.ranked_candidates[0]
    assert top_cand.rank == 1
    assert "Fulvestrant" in top_cand.recommended_combination or "endocrine" in top_cand.recommended_combination.lower()
    assert "HER2 kinase" in top_cand.mechanistic_synergy or "selectiv" in top_cand.mechanistic_synergy.lower()
    assert len(top_cand.evidence_citations) > 0



# ==============================================================================
# 7. Regulatory & Safety Invariant: Population Intelligence Disclaimer
# ==============================================================================

def test_mandatory_regulatory_disclaimer_present(
    patient_match_engine: PatientMatchEngine,
) -> None:
    """
    Verifies invariant:
    'Do not make patient-specific medical recommendations. This is drug-development population intelligence.'
    """
    profile = patient_match_engine.get_asset_patient_match("tucatinib")
    assert profile.disclaimer == POPULATION_INTELLIGENCE_DISCLAIMER
    assert "Do not make patient-specific medical recommendations" in profile.disclaimer
    assert "drug-development population intelligence" in profile.disclaimer

    scenario_res = patient_match_engine.match_cohort_scenario(PatientCohortQuery())
    assert scenario_res.disclaimer == POPULATION_INTELLIGENCE_DISCLAIMER
    assert "Do not make patient-specific medical recommendations" in scenario_res.disclaimer


# ==============================================================================
# 8. FastAPI Endpoints Integration
# ==============================================================================

def test_fastapi_patient_match_benchmarks(client: TestClient) -> None:
    response = client.get("/api/v1/patient-match/benchmarks")
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


def test_fastapi_patient_match_asset_by_id(client: TestClient) -> None:
    response = client.get("/api/v1/patient-match/asset/zongertinib")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "zongertinib"
    assert data["best_patient_population"]["tier"] == "BEST_PATIENT_POPULATION"
    assert data["secondary_patient_population"]["tier"] == "SECONDARY_PATIENT_POPULATION"
    assert data["excluded_patient_population"]["tier"] == "EXCLUDED_LOW_LIKELIHOOD_POPULATION"
    assert data["patient_match_score"] > 80.0
    assert POPULATION_INTELLIGENCE_DISCLAIMER in data["disclaimer"]


def test_fastapi_patient_match_fallback_asset(client: TestClient) -> None:
    response = client.get("/api/v1/patient-match/asset/novel-candidate-99")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "novel-candidate-99"
    assert data["best_patient_population"]["tier"] == "BEST_PATIENT_POPULATION"
    assert data["disclaimer"] == POPULATION_INTELLIGENCE_DISCLAIMER


def test_fastapi_patient_match_scenario_endpoint(client: TestClient) -> None:
    payload = {
        "disease_subtype": "ER+/HER2-mutant Metastatic Breast Cancer",
        "mutation": "HER2 L755S kinase domain",
        "expression": "ER+",
        "amplification": "Non-amplified",
        "protein_expression": "ER Allred 8, HER2 1+",
        "biomarker": "ER+/HER2-mutant",
        "prior_therapy": ["CDK4/6 inhibitor (palbociclib)", "Letrozole"],
        "resistance_state": "Post-CDK4/6 progression",
        "line_of_therapy": "2L+",
        "cns_status": "High risk CNS",
    }
    response = client.post("/api/v1/patient-match/scenario", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["best_matched_asset"]["asset_id"] == "zongertinib"
    assert len(data["ranked_candidates"]) > 0
    assert data["ranked_candidates"][0]["asset_id"] == "zongertinib"
    assert data["disclaimer"] == POPULATION_INTELLIGENCE_DISCLAIMER
