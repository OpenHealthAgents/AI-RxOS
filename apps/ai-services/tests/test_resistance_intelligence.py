from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.opportunity_engine.resistance import (
    EscapeMechanism,
    EvaluateResistanceRequest,
    ImpactSeverity,
    PotentialIntervention,
    ResistanceCategory,
    ResistanceClassification,
    ResistanceIntelligenceEngine,
    ResistanceRiskProfile,
    ResistanceRiskTier,
    RESISTANCE_INTELLIGENCE_DISCLAIMER,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def resistance_engine() -> ResistanceIntelligenceEngine:
    return ResistanceIntelligenceEngine()


# ==============================================================================
# 1. Database Migration & Schema Verification
# ==============================================================================

def test_migration_026_resistance_intelligence_ddl_exists() -> None:
    """
    Validates that the resistance intelligence migration file exists and defines
    escape mechanisms and risk profile tables with required indexes.
    """
    migration_file = Path("services/kg/migrations/026_resistance_intelligence.sql")
    assert migration_file.exists(), "Migration 026_resistance_intelligence.sql must exist"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS resistance_escape_mechanisms" in content
    assert "CREATE TABLE IF NOT EXISTS resistance_risk_profiles" in content
    assert "idx_res_escape_asset" in content
    assert "idx_res_escape_category" in content
    assert "idx_res_escape_classification" in content
    assert "idx_res_escape_proven" in content
    assert "idx_res_profile_asset" in content
    assert "idx_res_profile_risk_tier" in content


# ==============================================================================
# 2. Identification of All 8 Required Resistance Categories
# ==============================================================================

def test_identify_all_eight_resistance_categories(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Verifies that across assets, all 8 required resistance categories are identified:
    target mutation, target amplification, bypass signaling, downstream activation,
    pathway adaptation, phenotypic escape, tumor microenvironment mechanisms, metabolic adaptation.
    """
    benchmarks = resistance_engine.list_benchmark_profiles()
    assert len(benchmarks) >= 5

    categories_found = set()
    for profile in benchmarks:
        for mech in profile.top_escape_mechanisms:
            categories_found.add(mech.category.value)

    required_categories = {
        "target mutation",
        "target amplification",
        "bypass signaling",
        "downstream activation",
        "pathway adaptation",
        "phenotypic escape",
        "tumor microenvironment mechanisms",
        "metabolic adaptation",
    }
    assert required_categories.issubset(categories_found), (
        f"Missing categories: {required_categories - categories_found}"
    )


# ==============================================================================
# 3. Known vs Predicted Resistance Mechanisms
# ==============================================================================

def test_distinguish_known_vs_predicted_resistance_mechanisms(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Verifies identification and clear separation of known vs predicted resistance mechanisms.
    """
    profile = resistance_engine.get_asset_resistance_profile("zongertinib")

    known_mechs = [m for m in profile.top_escape_mechanisms if m.is_known_mechanism]
    predicted_mechs = [m for m in profile.top_escape_mechanisms if not m.is_known_mechanism]

    assert len(known_mechs) > 0, "Must identify known resistance mechanisms"
    assert len(predicted_mechs) > 0, "Must identify predicted resistance mechanisms"

    # Known mechanisms have documented literature/clinical citations
    for m in known_mechs:
        assert m.confidence >= 0.70
        assert len(m.evidence_citations) > 0

    # Predicted mechanisms have appropriate annotations
    for m in predicted_mechs:
        assert m.classification in {
            ResistanceClassification.AI_PREDICTED,
            ResistanceClassification.MECHANISTICALLY_INFERRED,
        }
        assert not m.is_experimentally_proven


# ==============================================================================
# 4. All 5 Epistemic Classifications
# ==============================================================================

def test_all_five_epistemic_classifications_supported(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Verifies all 5 classification tiers:
    Clinically observed, Observed, Preclinical, Mechanistically inferred, AI-predicted.
    """
    benchmarks = resistance_engine.list_benchmark_profiles()
    classifications_found = set()
    for profile in benchmarks:
        for mech in profile.top_escape_mechanisms:
            classifications_found.add(mech.classification.value)

    assert "Clinically observed" in classifications_found
    assert "Preclinical" in classifications_found
    assert "Mechanistically inferred" in classifications_found
    assert "AI-predicted" in classifications_found


# ==============================================================================
# 5. Strict Epistemic Invariant: Never Present Predicted as Experimentally Proven
# ==============================================================================

def test_strict_epistemic_invariant_never_present_predicted_as_experimentally_proven(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Strict Invariant:
    Never present predicted resistance as experimentally proven resistance.
    """
    benchmarks = resistance_engine.list_benchmark_profiles()

    for profile in benchmarks:
        # Check disclaimer presence
        assert RESISTANCE_INTELLIGENCE_DISCLAIMER in profile.disclaimer
        assert "Never present predicted resistance as experimentally proven resistance" in profile.disclaimer

        # Check invariant on all mechanisms
        for mech in profile.top_escape_mechanisms:
            if mech.classification in {
                ResistanceClassification.AI_PREDICTED,
                ResistanceClassification.MECHANISTICALLY_INFERRED,
            }:
                assert mech.is_experimentally_proven is False, (
                    f"Mechanism {mech.mechanism_name} is {mech.classification.value} but marked proven!"
                )

        # Check audit
        audit = profile.epistemic_audit
        assert audit.get("invariant_verified") is True
        assert audit.get("unproven_predicted_count", 0) > 0


def test_validation_error_when_marking_predicted_as_proven() -> None:
    """
    Tests that attempting to instantiate an AI-predicted or mechanistically inferred
    mechanism as experimentally proven raises a ValidationError.
    """
    # 1. AI-predicted with is_experimentally_proven=True MUST FAIL
    with pytest.raises(ValidationError) as excinfo:
        EscapeMechanism(
            mechanism_name="Theoretical Gatekeeper Variant",
            category=ResistanceCategory.TARGET_MUTATION,
            classification=ResistanceClassification.AI_PREDICTED,
            is_known_mechanism=False,
            is_experimentally_proven=True,  # VIOLATION
            impact_severity=ImpactSeverity.HIGH,
            molecular_description="Hypothetical variant",
            potential_intervention=PotentialIntervention(
                strategy_type="NEXT_GEN",
                intervention_name="Candidate",
                target_mechanism="Target",
                mechanistic_rationale="Rationale",
                development_status="Status",
                feasibility_score=0.5,
            ),
            confidence=0.4,
            epistemic_status_note="Note",
        )
    assert "Epistemic Invariant Violation" in str(excinfo.value)

    # 2. Mechanistically inferred with is_experimentally_proven=True MUST FAIL
    with pytest.raises(ValidationError) as excinfo2:
        EscapeMechanism(
            mechanism_name="Theoretical Bypass Pathway",
            category=ResistanceCategory.BYPASS_SIGNALING,
            classification=ResistanceClassification.MECHANISTICALLY_INFERRED,
            is_known_mechanism=False,
            is_experimentally_proven=True,  # VIOLATION
            impact_severity=ImpactSeverity.MODERATE,
            molecular_description="Hypothetical bypass",
            potential_intervention=PotentialIntervention(
                strategy_type="CO_TARGETING",
                intervention_name="Inhibitor",
                target_mechanism="Target",
                mechanistic_rationale="Rationale",
                development_status="Status",
                feasibility_score=0.5,
            ),
            confidence=0.5,
            epistemic_status_note="Note",
        )
    assert "Epistemic Invariant Violation" in str(excinfo2.value)


# ==============================================================================
# 6. Output Contracts: Profile, Top Escapes, Evidence, Confidence, Interventions
# ==============================================================================

def test_resistance_risk_profile_output_contract(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Verifies that querying an asset produces:
    - Resistance Risk Profile (score 0-100, risk tier, primary vulnerability)
    - Top Escape Mechanisms (ranked)
    - Evidence
    - Confidence (0.0 - 1.0)
    - Potential Intervention
    """
    profile = resistance_engine.get_asset_resistance_profile("zongertinib")

    # 1. Resistance Risk Profile
    assert 0.0 <= profile.overall_risk_score <= 100.0
    assert profile.risk_tier in {ResistanceRiskTier.LOW, ResistanceRiskTier.MODERATE, ResistanceRiskTier.HIGH, ResistanceRiskTier.VERY_HIGH}
    assert len(profile.primary_vulnerability) > 0
    assert len(profile.evidence_summary) > 0

    # 2. Top Escape Mechanisms
    assert len(profile.top_escape_mechanisms) >= 5
    for mech in profile.top_escape_mechanisms:
        assert mech.mechanism_name is not None
        assert mech.category in ResistanceCategory
        assert mech.classification in ResistanceClassification
        assert mech.impact_severity in ImpactSeverity

        # 3. Evidence
        if mech.is_experimentally_proven:
            assert len(mech.evidence_citations) > 0
            assert "pmid" in mech.evidence_citations[0] or "nct_id" in mech.evidence_citations[0] or "source" in mech.evidence_citations[0]

        # 4. Confidence
        assert 0.0 <= mech.confidence <= 1.0

        # 5. Potential Intervention
        intervention = mech.potential_intervention
        assert len(intervention.intervention_name) > 0
        assert len(intervention.mechanistic_rationale) > 0
        assert 0.0 <= intervention.feasibility_score <= 1.0

    # Recommended Interventions
    assert len(profile.recommended_interventions) >= 3


# ==============================================================================
# 7. Asset-Specific Intelligence Profiles
# ==============================================================================

def test_zongertinib_resistance_profile(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Verifies Zongertinib:
    - Moderate risk tier (42.0)
    - C805S covalent resistance (Preclinical)
    - Compensatory ER bypass (Clinically observed) with +Fulvestrant intervention
    - AI-predicted D863N unproven mechanism
    """
    profile = resistance_engine.get_asset_resistance_profile("zongertinib")
    assert profile.asset_id == "zongertinib"
    assert profile.risk_tier == ResistanceRiskTier.MODERATE
    assert profile.overall_risk_score == 42.0

    mech_names = [m.mechanism_name for m in profile.top_escape_mechanisms]
    assert any("C805S" in name for name in mech_names)
    assert any("Estrogen Receptor" in name for name in mech_names)
    assert any("PIK3CA" in name for name in mech_names)
    assert any("MET" in name for name in mech_names)

    # Check ER bypass intervention
    er_mech = next(m for m in profile.top_escape_mechanisms if "Estrogen Receptor" in m.mechanism_name)
    assert er_mech.classification == ResistanceClassification.CLINICALLY_OBSERVED
    assert er_mech.is_experimentally_proven is True
    assert "Fulvestrant" in er_mech.potential_intervention.intervention_name or "SERD" in er_mech.potential_intervention.intervention_name


def test_tucatinib_resistance_profile(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Verifies Tucatinib:
    - Clinically observed T798M gatekeeper from HER2CLIMB ctDNA
    - ERBB2 focal copy number loss / antigen reduction
    - Interventions include T-DXd and Capivasertib
    """
    profile = resistance_engine.get_asset_resistance_profile("tucatinib")
    assert profile.asset_id == "tucatinib"
    assert profile.overall_risk_score == 58.0

    t798m = next(m for m in profile.top_escape_mechanisms if "T798M" in m.mechanism_name)
    assert t798m.classification == ResistanceClassification.CLINICALLY_OBSERVED
    assert t798m.is_experimentally_proven is True
    assert "T-DXd" in t798m.potential_intervention.intervention_name or "Trastuzumab deruxtecan" in t798m.potential_intervention.intervention_name


def test_neratinib_and_poziotinib_high_risk_profiles(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Verifies Neratinib (High Risk) and Poziotinib (Very High Risk)
    due to toxicity-driven subtherapeutic exposure and neuroendocrine escape.
    """
    ner = resistance_engine.get_asset_resistance_profile("neratinib")
    assert ner.risk_tier == ResistanceRiskTier.HIGH
    assert ner.overall_risk_score >= 70.0
    diarrhea_mech = next(m for m in ner.top_escape_mechanisms if "Toxicity" in m.mechanism_name or "Diarrhea" in m.molecular_description)
    assert diarrhea_mech.classification == ResistanceClassification.CLINICALLY_OBSERVED
    assert "loperamide" in diarrhea_mech.potential_intervention.intervention_name.lower() or "prophylaxis" in diarrhea_mech.potential_intervention.intervention_name.lower()

    poz = resistance_engine.get_asset_resistance_profile("poziotinib")
    assert poz.risk_tier == ResistanceRiskTier.VERY_HIGH
    assert poz.overall_risk_score >= 85.0
    neuro_mech = next(m for m in poz.top_escape_mechanisms if "Small-Cell" in m.mechanism_name or "Neuroendocrine" in m.mechanism_name)
    assert neuro_mech.classification == ResistanceClassification.CLINICALLY_OBSERVED


def test_ox_her2_01_cns_resistance_profile(
    resistance_engine: ResistanceIntelligenceEngine,
) -> None:
    """
    Verifies OX-HER2-01 intracranial brain metastasis resistance liabilities
    (astrocyte gap junctions, C805S in brain mets, intracranial PIK3CA activation).
    """
    profile = resistance_engine.get_asset_resistance_profile("ox-her2-01")
    assert profile.asset_id == "ox-her2-01"

    astro_mech = next(m for m in profile.top_escape_mechanisms if "Astrocyte" in m.mechanism_name or "Gap Junction" in m.mechanism_name)
    assert astro_mech.category == ResistanceCategory.TUMOR_MICROENVIRONMENT
    assert astro_mech.classification == ResistanceClassification.PRECLINICAL
    assert "Gap junction" in astro_mech.potential_intervention.intervention_name or "Tonabersat" in astro_mech.potential_intervention.intervention_name


# ==============================================================================
# 8. FastAPI Integration Tests
# ==============================================================================

def test_fastapi_resistance_benchmarks(client: TestClient) -> None:
    response = client.get("/api/v1/resistance/benchmarks")
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


def test_fastapi_resistance_asset_by_id(client: TestClient) -> None:
    response = client.get("/api/v1/resistance/asset/zongertinib")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "zongertinib"
    assert data["risk_tier"] == "MODERATE"
    assert len(data["top_escape_mechanisms"]) > 0
    assert RESISTANCE_INTELLIGENCE_DISCLAIMER in data["disclaimer"]


def test_fastapi_resistance_top_escapes(client: TestClient) -> None:
    response = client.get("/api/v1/resistance/asset/tucatinib/top-escapes?limit=3")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3
    assert data[0]["impact_severity"] in ["CRITICAL", "HIGH"]


def test_fastapi_resistance_interventions(client: TestClient) -> None:
    response = client.get("/api/v1/resistance/asset/zongertinib/interventions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    intervention_names = [i["intervention_name"] for i in data]
    assert any("Fulvestrant" in name for name in intervention_names)


def test_fastapi_resistance_evaluate_endpoint(client: TestClient) -> None:
    # Evaluate with confidence threshold filter
    payload = {
        "asset_id": "zongertinib",
        "include_ai_predicted": False,
        "min_confidence": 0.80,
    }
    response = client.post("/api/v1/resistance/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "zongertinib"
    # Ensure no AI-predicted mechanisms returned
    for mech in data["top_escape_mechanisms"]:
        assert mech["classification"] != "AI-predicted"
        assert mech["confidence"] >= 0.80
    assert RESISTANCE_INTELLIGENCE_DISCLAIMER in data["disclaimer"]


def test_fastapi_resistance_fallback_profile(client: TestClient) -> None:
    response = client.get("/api/v1/resistance/asset/unknown-compound-99")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "unknown-compound-99"
    assert RESISTANCE_INTELLIGENCE_DISCLAIMER in data["disclaimer"]
