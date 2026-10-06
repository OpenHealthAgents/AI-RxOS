from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.opportunity_engine.combination import (
    ClinicalEvidenceEvaluation,
    CombinationIntelligenceEngine,
    CombinationIntelligenceProfile,
    CombinationValidationStatus,
    CompetitiveCombinationReference,
    DevelopmentFeasibilityEvaluation,
    DevelopmentRiskTier,
    EvaluateCombinationQuery,
    ExistingCombinationReference,
    MechanisticComplementarityEvaluation,
    PharmacologicalFeasibilityEvaluation,
    PreclinicalEvidenceEvaluation,
    RecommendedCombinationStrategy,
    ToxicityOverlapEvaluation,
    ToxicityOverlapSeverity,
    COMBINATION_INTELLIGENCE_DISCLAIMER,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def combination_engine() -> CombinationIntelligenceEngine:
    return CombinationIntelligenceEngine()


# ==============================================================================
# 1. Database Migration & Schema Verification
# ==============================================================================

def test_migration_027_combination_intelligence_ddl_exists() -> None:
    """
    Validates that the combination intelligence migration file exists and defines
    combination strategies and evaluation tables with required indexes.
    """
    migration_file = Path("services/kg/migrations/027_combination_intelligence.sql")
    assert migration_file.exists(), "Migration 027_combination_intelligence.sql must exist"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS combination_strategies" in content
    assert "CREATE TABLE IF NOT EXISTS combination_intelligence_evaluations" in content
    assert "idx_comb_strat_primary" in content
    assert "idx_comb_strat_partner" in content
    assert "idx_comb_strat_mech" in content
    assert "idx_comb_strat_status" in content
    assert "idx_comb_strat_risk" in content


# ==============================================================================
# 2. Evaluation Across All 8 Core Dimensions
# ==============================================================================

def test_evaluation_across_all_eight_core_dimensions(
    combination_engine: CombinationIntelligenceEngine,
) -> None:
    """
    Verifies that combination strategies evaluate all 8 core dimensions:
    mechanistic complementarity, preclinical evidence, clinical evidence,
    toxicity overlap, pharmacological feasibility, development feasibility,
    existing combinations, and competitive combinations.
    """
    profile = combination_engine.get_asset_combination_profile("zongertinib")
    combo = profile.primary_combination

    # 1. Mechanistic Complementarity
    assert combo.mechanistic_complementarity.synergy_mechanism is not None
    assert len(combo.mechanistic_complementarity.biological_rationale) > 0
    assert combo.mechanistic_complementarity.pathway_target is not None

    # 2. Preclinical Evidence
    assert combo.preclinical_evidence.in_vitro_synergy is not None
    assert len(combo.preclinical_evidence.in_vivo_models) > 0
    assert combo.preclinical_evidence.tumor_growth_inhibition_pct is not None

    # 3. Clinical Evidence
    assert combo.clinical_evidence.trial_phase is not None
    assert len(combo.clinical_evidence.citations) > 0

    # 4. Toxicity Overlap
    assert combo.toxicity_overlap.overlap_severity in ToxicityOverlapSeverity
    assert len(combo.toxicity_overlap.mitigation_strategy) > 0

    # 5. Pharmacological Feasibility
    assert combo.pharmacological_feasibility.cyp_interaction_risk is not None
    assert 0.0 <= combo.pharmacological_feasibility.pk_ddi_score <= 1.0

    # 6. Development Feasibility
    assert combo.development_feasibility.sponsor_landscape is not None
    assert 0.0 <= combo.development_feasibility.feasibility_score <= 1.0

    # 7. Existing Combinations
    assert len(combo.existing_combinations) > 0

    # 8. Competitive Combinations
    assert len(combo.competitive_combinations) > 0


# ==============================================================================
# 3. Epistemic Separation & Strict Invariant
# ==============================================================================

def test_strict_epistemic_distinction_and_invariants(
    combination_engine: CombinationIntelligenceEngine,
) -> None:
    """
    Clearly distinguishes:
    clinically validated, preclinical supported, mechanistically plausible, AI-generated hypothesis.
    Strict Invariant:
    Never present an AI-generated hypothesis or mechanistically plausible combination as clinically validated.
    """
    benchmarks = combination_engine.list_benchmark_combination_profiles()
    all_statuses = set()

    for p in benchmarks:
        assert COMBINATION_INTELLIGENCE_DISCLAIMER in p.disclaimer
        for c in p.recommended_combinations:
            all_statuses.add(c.validation_status.value)
            if c.validation_status in {
                CombinationValidationStatus.AI_GENERATED_HYPOTHESIS,
                CombinationValidationStatus.MECHANISTICALLY_PLAUSIBLE,
            }:
                assert c.is_clinically_validated is False

    assert "clinically validated" in all_statuses
    assert "preclinical supported" in all_statuses
    assert "mechanistically plausible" in all_statuses
    assert "AI-generated hypothesis" in all_statuses


def test_validation_error_when_marking_unproven_combination_as_validated() -> None:
    """
    Verifies that attempting to mark an AI-generated hypothesis or mechanistically plausible
    combination as clinically validated raises a ValidationError.
    """
    # 1. AI-generated marked as clinically validated
    with pytest.raises(ValidationError) as exc1:
        RecommendedCombinationStrategy(
            regimen_name="Hypothetical Pair",
            primary_asset_id="asset1",
            primary_asset_name="Asset 1",
            partner_name="Partner X",
            partner_class="Experimental Class",
            resistance_mechanism_addressed="Bypass",
            resistance_category="bypass signaling",
            validation_status=CombinationValidationStatus.AI_GENERATED_HYPOTHESIS,
            is_clinically_validated=True,  # VIOLATION
            mechanistic_complementarity=MechanisticComplementarityEvaluation(
                synergy_mechanism="Hypothetical",
                biological_rationale="Rationale",
                pathway_target="Target",
                escape_suppression_mode="Mode",
            ),
            preclinical_evidence=PreclinicalEvidenceEvaluation(summary="None"),
            clinical_evidence=ClinicalEvidenceEvaluation(summary="None"),
            toxicity_overlap=ToxicityOverlapEvaluation(
                overlap_severity=ToxicityOverlapSeverity.MINIMAL,
                therapeutic_window_impact="Impact",
                mitigation_strategy="Strategy",
            ),
            pharmacological_feasibility=PharmacologicalFeasibilityEvaluation(
                cyp_interaction_risk="Clean",
                efflux_interaction="Low",
                schedule_compatibility="Daily",
                pk_ddi_score=0.9,
            ),
            development_feasibility=DevelopmentFeasibilityEvaluation(
                sponsor_landscape="Single",
                regulatory_pathway="Phase 1",
                ip_freedom="Clear",
                feasibility_score=0.8,
            ),
            rationale="Test",
            confidence=0.4,
            development_risk_score=70.0,
            development_risk_tier=DevelopmentRiskTier.HIGH,
        )
    assert "Epistemic Invariant Violation" in str(exc1.value)

    # 2. Mechanistically plausible marked as clinically validated
    with pytest.raises(ValidationError) as exc2:
        RecommendedCombinationStrategy(
            regimen_name="Plausible Pair",
            primary_asset_id="asset2",
            primary_asset_name="Asset 2",
            partner_name="Partner Y",
            partner_class="Approved Class",
            resistance_mechanism_addressed="Adaptation",
            resistance_category="pathway adaptation",
            validation_status=CombinationValidationStatus.MECHANISTICALLY_PLAUSIBLE,
            is_clinically_validated=True,  # VIOLATION
            mechanistic_complementarity=MechanisticComplementarityEvaluation(
                synergy_mechanism="Plausible",
                biological_rationale="Rationale",
                pathway_target="Target",
                escape_suppression_mode="Mode",
            ),
            preclinical_evidence=PreclinicalEvidenceEvaluation(summary="None"),
            clinical_evidence=ClinicalEvidenceEvaluation(summary="None"),
            toxicity_overlap=ToxicityOverlapEvaluation(
                overlap_severity=ToxicityOverlapSeverity.MINIMAL,
                therapeutic_window_impact="Impact",
                mitigation_strategy="Strategy",
            ),
            pharmacological_feasibility=PharmacologicalFeasibilityEvaluation(
                cyp_interaction_risk="Clean",
                efflux_interaction="Low",
                schedule_compatibility="Daily",
                pk_ddi_score=0.9,
            ),
            development_feasibility=DevelopmentFeasibilityEvaluation(
                sponsor_landscape="Single",
                regulatory_pathway="Phase 1",
                ip_freedom="Clear",
                feasibility_score=0.8,
            ),
            rationale="Test",
            confidence=0.5,
            development_risk_score=50.0,
            development_risk_tier=DevelopmentRiskTier.MODERATE,
        )
    assert "Epistemic Invariant Violation" in str(exc2.value)


# ==============================================================================
# 4. Output Contracts: Regimen, Rationale, Evidence, Mechanism, Confidence, Risk
# ==============================================================================

def test_combination_output_contract_fields(
    combination_engine: CombinationIntelligenceEngine,
) -> None:
    """
    Verifies that all combination outputs contain:
    Recommended Combination, Rationale, Evidence, Resistance mechanism addressed,
    Confidence, Development Risk.
    """
    profile = combination_engine.get_asset_combination_profile("zongertinib")
    combo = profile.primary_combination

    # Recommended Combination
    assert "Zongertinib" in combo.regimen_name
    assert combo.partner_name == "Fulvestrant"

    # Rationale
    assert len(combo.rationale) > 0

    # Evidence
    assert len(combo.evidence_citations) > 0
    assert "pmid" in combo.evidence_citations[0]

    # Resistance mechanism addressed
    assert "Estrogen Receptor" in combo.resistance_mechanism_addressed

    # Confidence
    assert 0.0 <= combo.confidence <= 1.0

    # Development Risk
    assert 0.0 <= combo.development_risk_score <= 100.0
    assert combo.development_risk_tier in DevelopmentRiskTier


# ==============================================================================
# 5. Asset-Specific Intelligence Profiles
# ==============================================================================

def test_zongertinib_combination_portfolio(
    combination_engine: CombinationIntelligenceEngine,
) -> None:
    """
    Verifies Zongertinib combinations:
    - Primary: + Fulvestrant (clinically validated in MutHER, Low risk)
    - + Capivasertib (preclinical supported, Moderate risk)
    - + Tepotinib (preclinical supported)
    - + AI-Generated allosteric stabilizer (AI-generated hypothesis, High risk)
    """
    profile = combination_engine.get_asset_combination_profile("zongertinib")
    assert profile.asset_id == "zongertinib"
    assert len(profile.recommended_combinations) == 4

    primary = profile.primary_combination
    assert primary.partner_name == "Fulvestrant"
    assert primary.validation_status == CombinationValidationStatus.CLINICALLY_VALIDATED
    assert primary.is_clinically_validated is True
    assert primary.development_risk_tier == DevelopmentRiskTier.LOW

    # Verify presence of AI-generated hypothesis
    ai_combo = next(c for c in profile.recommended_combinations if c.validation_status == CombinationValidationStatus.AI_GENERATED_HYPOTHESIS)
    assert "Allosteric" in ai_combo.partner_class
    assert ai_combo.is_clinically_validated is False
    assert ai_combo.development_risk_tier == DevelopmentRiskTier.HIGH


def test_tucatinib_combination_portfolio(
    combination_engine: CombinationIntelligenceEngine,
) -> None:
    """
    Verifies Tucatinib combinations:
    - Tucatinib + Trastuzumab + Capecitabine (clinically validated in HER2CLIMB, Low risk)
    - Tucatinib + T-DXd (clinically validated in HER2CLIMB-04)
    - Tucatinib + Lumretuzumab (mechanistically plausible)
    """
    profile = combination_engine.get_asset_combination_profile("tucatinib")
    assert profile.asset_id == "tucatinib"

    triplet = profile.primary_combination
    assert "Capecitabine" in triplet.regimen_name
    assert triplet.validation_status == CombinationValidationStatus.CLINICALLY_VALIDATED

    tdxd_combo = next(c for c in profile.recommended_combinations if "T-DXd" in c.regimen_name)
    assert tdxd_combo.validation_status == CombinationValidationStatus.CLINICALLY_VALIDATED
    assert "T798M" in tdxd_combo.resistance_mechanism_addressed

    her3_combo = next(c for c in profile.recommended_combinations if c.validation_status == CombinationValidationStatus.MECHANISTICALLY_PLAUSIBLE)
    assert "HER3" in her3_combo.partner_name or "HER3" in her3_combo.resistance_mechanism_addressed


def test_neratinib_and_poziotinib_combinations(
    combination_engine: CombinationIntelligenceEngine,
) -> None:
    """
    Verifies Neratinib prophylaxis combination and Poziotinib class substitution.
    """
    ner = combination_engine.get_asset_combination_profile("neratinib")
    assert "Loperamide" in ner.primary_combination.partner_name
    assert ner.primary_combination.validation_status == CombinationValidationStatus.CLINICALLY_VALIDATED

    poz = combination_engine.get_asset_combination_profile("poziotinib")
    assert "Zongertinib" in poz.primary_combination.regimen_name
    assert poz.primary_combination.validation_status == CombinationValidationStatus.CLINICALLY_VALIDATED


def test_ox_her2_01_cns_combinations(
    combination_engine: CombinationIntelligenceEngine,
) -> None:
    """
    Verifies OX-HER2-01 + Paxalisib dual brain-penetrant combination for intracranial PIK3CA activation.
    """
    profile = combination_engine.get_asset_combination_profile("ox-her2-01")
    combo = profile.primary_combination
    assert "Paxalisib" in combo.partner_name
    assert combo.validation_status == CombinationValidationStatus.PRECLINICAL_SUPPORTED
    assert "PIK3CA" in combo.resistance_mechanism_addressed


# ==============================================================================
# 6. Mechanism-Based Combination Discovery
# ==============================================================================

def test_find_combinations_by_resistance_mechanism(
    combination_engine: CombinationIntelligenceEngine,
) -> None:
    """
    Tests finding combination strategies for specific resistance mechanisms.
    """
    # 1. Estrogen Receptor bypass
    er_combos = combination_engine.find_combinations_for_resistance_mechanism("Estrogen Receptor")
    assert len(er_combos) >= 1
    assert any("Fulvestrant" in c.partner_name for c in er_combos)

    # 2. T798M gatekeeper
    t798m_combos = combination_engine.find_combinations_for_resistance_mechanism("T798M")
    assert len(t798m_combos) >= 1
    assert any("T-DXd" in c.regimen_name for c in t798m_combos)

    # 3. PIK3CA downstream mutation
    pi3k_combos = combination_engine.find_combinations_for_resistance_mechanism("PIK3CA")
    assert len(pi3k_combos) >= 2


# ==============================================================================
# 7. FastAPI Integration Tests
# ==============================================================================

def test_fastapi_combination_benchmarks(client: TestClient) -> None:
    response = client.get("/api/v1/combination/benchmarks")
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


def test_fastapi_combination_asset_profile(client: TestClient) -> None:
    response = client.get("/api/v1/combination/asset/zongertinib")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "zongertinib"
    assert data["primary_combination"]["partner_name"] == "Fulvestrant"
    assert COMBINATION_INTELLIGENCE_DISCLAIMER in data["disclaimer"]


def test_fastapi_combination_by_mechanism(client: TestClient) -> None:
    response = client.get("/api/v1/combination/mechanism?name=Estrogen%20Receptor")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "Fulvestrant" in data[0]["partner_name"]


def test_fastapi_combination_evaluate_endpoint(client: TestClient) -> None:
    # Filter for low-risk, clinically validated combinations
    payload = {
        "asset_id": "zongertinib",
        "min_confidence": 0.90,
        "max_risk_tier": "LOW",
        "include_ai_generated": False,
    }
    response = client.post("/api/v1/combination/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    for c in data:
        assert c["confidence"] >= 0.90
        assert c["development_risk_tier"] == "LOW"
        assert c["validation_status"] != "AI-generated hypothesis"


def test_fastapi_combination_fallback(client: TestClient) -> None:
    response = client.get("/api/v1/combination/asset/novel-candidate-99")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "novel-candidate-99"
    assert COMBINATION_INTELLIGENCE_DISCLAIMER in data["disclaimer"]
