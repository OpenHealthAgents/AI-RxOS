from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.competitive.engine import (
    CANONICAL_COMPETITORS,
    CompetitiveIntelligenceEngine,
)
from app.opportunity_engine.competitive.models import (
    ComparisonAdvantagePolarity,
    CompetitiveDensityTier,
    CompetitiveRiskTier,
    DifferentiationTier,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def engine() -> CompetitiveIntelligenceEngine:
    return CompetitiveIntelligenceEngine()


# ==============================================================================
# 1. Benchmark Profiles & Invariants
# ==============================================================================

def test_benchmark_profiles_loaded(engine: CompetitiveIntelligenceEngine) -> None:
    benchmarks = engine.list_benchmark_profiles()
    assert len(benchmarks) >= 5
    asset_ids = {b.asset_id for b in benchmarks}
    assert "zongertinib" in asset_ids
    assert "tucatinib" in asset_ids
    assert "neratinib" in asset_ids
    assert "poziotinib" in asset_ids
    assert "ox-her2-01" in asset_ids


def test_canonical_competitors_catalog(engine: CompetitiveIntelligenceEngine) -> None:
    competitors = engine.list_all_competitors()
    assert len(competitors) >= 7
    comp_ids = {c.competitor_id for c in competitors}
    assert "tdxd" in comp_ids
    assert "bay_2927088" in comp_ids
    assert "tucatinib" in comp_ids
    assert "neratinib" in comp_ids
    assert "poziotinib" in comp_ids
    assert "dfci_protac_her2" in comp_ids
    assert "mda_exon20_allosteric" in comp_ids
    assert "ox_her2_01" in comp_ids


# ==============================================================================
# 2. Competitor Identification across 10 Cohorts
# ==============================================================================

def test_zongertinib_competitor_cohorts(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.get_competitive_profile("zongertinib")
    assert profile is not None
    cohorts = profile.cohorts

    # 1. Direct competitors
    direct_ids = {c.competitor_id for c in cohorts.direct_competitors}
    assert "bay_2927088" in direct_ids
    assert "poziotinib" in direct_ids

    # 2. Same target
    target_ids = {c.competitor_id for c in cohorts.same_target}
    assert "tdxd" in target_ids
    assert "tucatinib" in target_ids
    assert "neratinib" in target_ids

    # 3. Same mechanism (covalent kinase inhibitor)
    mech_ids = {c.competitor_id for c in cohorts.same_mechanism}
    assert "neratinib" in mech_ids
    assert "poziotinib" in mech_ids

    # 4. Same biomarker (exon 20 insertions & TKD mutants)
    bio_ids = {c.competitor_id for c in cohorts.same_biomarker}
    assert "tdxd" in bio_ids
    assert "bay_2927088" in bio_ids

    # 5. Same indication (HER2 NSCLC)
    ind_ids = {c.competitor_id for c in cohorts.same_indication}
    assert "tdxd" in ind_ids
    assert "bay_2927088" in ind_ids

    # 6. Same patient population (Pretreated HER2-mutant NSCLC)
    pop_ids = {c.competitor_id for c in cohorts.same_patient_population}
    assert "tdxd" in pop_ids
    assert "bay_2927088" in pop_ids

    # 7. Same modality (Small Molecule TKI)
    mod_ids = {c.competitor_id for c in cohorts.same_modality}
    assert "bay_2927088" in mod_ids
    assert "tucatinib" in mod_ids
    assert "neratinib" in mod_ids

    # 8. Clinical-stage competitors
    clin_ids = {c.competitor_id for c in cohorts.clinical_stage_competitors}
    assert "bay_2927088" in clin_ids
    assert "tucatinib" in clin_ids

    # 9. Approved standards of care
    soc_ids = {c.competitor_id for c in cohorts.approved_standards_of_care}
    assert "tdxd" in soc_ids
    assert "tucatinib" in soc_ids
    assert "neratinib" in soc_ids

    # 10. Emerging academic programs
    acad_ids = {c.competitor_id for c in cohorts.emerging_academic_programs}
    assert "dfci_protac_her2" in acad_ids
    assert "mda_exon20_allosteric" in acad_ids
    assert "ox_her2_01" in acad_ids


# ==============================================================================
# 3. Head-to-Head Comparisons across 11 Dimensions
# ==============================================================================

def test_zongertinib_vs_tdxd_eleven_dimensions(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.get_competitive_profile("zongertinib")
    assert profile is not None

    h2h_tdxd = next((h for h in profile.head_to_head_comparisons if h.competitor_id == "tdxd"), None)
    assert h2h_tdxd is not None
    assert h2h_tdxd.is_approved_soc is True

    # 1. Potency
    assert h2h_tdxd.potency.dimension_name == "Potency"
    assert "2.4 nM" in h2h_tdxd.potency.focal_value

    # 2. Selectivity
    assert h2h_tdxd.selectivity.dimension_name == "Selectivity"
    assert ">59x" in h2h_tdxd.selectivity.focal_value

    # 3. CNS
    assert h2h_tdxd.cns.dimension_name == "CNS Activity"
    assert h2h_tdxd.cns.polarity == ComparisonAdvantagePolarity.FAVORABLE
    assert h2h_tdxd.cns.advantage_delta_score > 0
    assert "41.2%" in h2h_tdxd.cns.focal_value

    # 4. Clinical Stage
    assert h2h_tdxd.clinical_stage.dimension_name == "Clinical Stage"
    assert h2h_tdxd.clinical_stage.polarity == ComparisonAdvantagePolarity.UNFAVORABLE
    assert h2h_tdxd.clinical_stage.advantage_delta_score < 0

    # 5. Efficacy
    assert h2h_tdxd.efficacy.dimension_name == "Efficacy"
    assert h2h_tdxd.efficacy.polarity == ComparisonAdvantagePolarity.FAVORABLE
    assert "73.8%" in h2h_tdxd.efficacy.focal_value

    # 6. Safety
    assert h2h_tdxd.safety.dimension_name == "Safety"
    assert h2h_tdxd.safety.polarity == ComparisonAdvantagePolarity.FAVORABLE
    assert h2h_tdxd.safety.advantage_delta_score > 5.0
    assert "ILD" in h2h_tdxd.safety.competitor_value

    # 7. Biomarker
    assert h2h_tdxd.biomarker.dimension_name == "Biomarker"

    # 8. Resistance
    assert h2h_tdxd.resistance.dimension_name == "Resistance"
    assert h2h_tdxd.resistance.polarity == ComparisonAdvantagePolarity.FAVORABLE

    # 9. Combination
    assert h2h_tdxd.combination.dimension_name == "Combination"
    assert "fulvestrant" in h2h_tdxd.combination.focal_value

    # 10. Ownership
    assert h2h_tdxd.ownership.dimension_name == "Ownership"
    assert "Boehringer" in h2h_tdxd.ownership.focal_value

    # 11. Commercial Opportunity
    assert h2h_tdxd.commercial_opportunity.dimension_name == "Commercial Opportunity"

    # Key differentiators list
    assert len(h2h_tdxd.key_differentiators) >= 3


def test_zongertinib_vs_bay_2927088_comparison(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.get_competitive_profile("zongertinib")
    assert profile is not None

    h2h_bay = next((h for h in profile.head_to_head_comparisons if h.competitor_id == "bay_2927088"), None)
    assert h2h_bay is not None
    assert h2h_bay.overall_advantage == ComparisonAdvantagePolarity.FAVORABLE
    # Safety advantage: wt-EGFR sparing
    assert h2h_bay.safety.polarity == ComparisonAdvantagePolarity.FAVORABLE
    assert h2h_bay.selectivity.polarity == ComparisonAdvantagePolarity.FAVORABLE


# ==============================================================================
# 4. Four Core Deliverables Verification
# ==============================================================================

def test_zongertinib_four_core_deliverables(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.get_competitive_profile("zongertinib")
    assert profile is not None

    # Deliverable 1: Competitive Density
    density = profile.competitive_density
    assert 0.0 <= density.density_score <= 100.0
    assert density.density_tier in (CompetitiveDensityTier.HIGH, CompetitiveDensityTier.MODERATE)
    assert density.direct_competitors_count == 2
    assert density.approved_soc_count >= 2

    # Deliverable 2: Differentiation Score
    diff = profile.differentiation
    assert diff.differentiation_score >= 80.0
    assert diff.differentiation_tier == DifferentiationTier.HIGHLY_DIFFERENTIATED
    assert len(diff.key_usps) >= 3

    # Deliverable 3: Competitive Risk
    risk = profile.competitive_risk
    assert 0.0 <= risk.risk_score <= 50.0
    assert risk.risk_tier == CompetitiveRiskTier.LOW
    assert len(risk.primary_threats) >= 1

    # Deliverable 4: White-Space Opportunities
    spaces = profile.white_space_opportunities
    assert len(spaces) >= 3
    niche_names = {s.niche_name for s in spaces}
    assert any("Brain Metastases" in n for n in niche_names)
    assert any("Post-ADC" in n or "Refractory" in n for n in niche_names)
    assert any("Breast Cancer" in n for n in niche_names)


# ==============================================================================
# 5. Benchmark Contrast: Tucatinib, Neratinib, Poziotinib, OX-HER2-01
# ==============================================================================

def test_tucatinib_benchmark(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.get_competitive_profile("tucatinib")
    assert profile is not None
    assert profile.competitive_density.density_tier == CompetitiveDensityTier.VERY_HIGH
    assert profile.differentiation.differentiation_tier == DifferentiationTier.HIGHLY_DIFFERENTIATED
    assert profile.differentiation.differentiation_score >= 80.0
    assert len(profile.head_to_head_comparisons) >= 1
    h2h_ner = profile.head_to_head_comparisons[0]
    assert h2h_ner.competitor_id == "neratinib"
    assert h2h_ner.selectivity.polarity == ComparisonAdvantagePolarity.FAVORABLE


def test_neratinib_benchmark(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.get_competitive_profile("neratinib")
    assert profile is not None
    assert profile.differentiation.differentiation_tier == DifferentiationTier.MINIMALLY_DIFFERENTIATED
    assert profile.differentiation.differentiation_score < 50.0
    assert profile.competitive_risk.risk_tier == CompetitiveRiskTier.HIGH
    assert profile.competitive_risk.risk_score >= 70.0


def test_poziotinib_benchmark(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.get_competitive_profile("poziotinib")
    assert profile is not None
    assert profile.differentiation.differentiation_tier == DifferentiationTier.UNDIFFERENTIATED
    assert profile.differentiation.differentiation_score < 30.0
    assert profile.competitive_risk.risk_tier == CompetitiveRiskTier.CRITICAL
    assert profile.competitive_risk.risk_score >= 90.0


def test_ox_her2_01_academic_lead(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.get_competitive_profile("ox-her2-01")
    assert profile is not None
    assert profile.stage == "Preclinical"
    assert profile.differentiation.differentiation_score >= 70.0
    assert len(profile.white_space_opportunities) >= 1
    assert "Leptomeningeal" in profile.white_space_opportunities[0].niche_name


# ==============================================================================
# 6. Dynamic Evaluation for Custom Unmodeled Assets
# ==============================================================================

def test_dynamic_evaluation_for_unmodeled_asset(engine: CompetitiveIntelligenceEngine) -> None:
    profile = engine.evaluate_competitive_landscape(
        asset_id="novel-her2-tki",
        asset_name="Novel HER2 Inhibitor",
        target="HER2",
        indication="Gastric Cancer",
        patient_population="HER2-positive advanced gastric cancer",
        modality="Small Molecule TKI",
        stage="Phase I",
    )
    assert profile.asset_id == "novel-her2-tki"
    assert profile.asset_name == "Novel HER2 Inhibitor"
    assert profile.target == "HER2"
    assert profile.primary_indication == "Gastric Cancer"
    assert profile.competitive_density.density_score > 0
    assert profile.differentiation.differentiation_score > 0
    assert profile.competitive_risk.risk_score > 0
    assert len(profile.white_space_opportunities) >= 1


# ==============================================================================
# 7. FastAPI Endpoints Integration
# ==============================================================================

def test_api_list_benchmarks(client: TestClient) -> None:
    resp = client.get("/api/v1/competitive/benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 5


def test_api_list_competitors(client: TestClient) -> None:
    resp = client.get("/api/v1/competitive/competitors")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 7


def test_api_get_asset_profile(client: TestClient) -> None:
    resp = client.get("/api/v1/competitive/asset/zongertinib")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "zongertinib"
    assert "competitive_density" in data
    assert "differentiation" in data
    assert "competitive_risk" in data
    assert "white_space_opportunities" in data
    assert len(data["white_space_opportunities"]) >= 3


def test_api_get_asset_cohorts(client: TestClient) -> None:
    resp = client.get("/api/v1/competitive/asset/zongertinib/cohorts")
    assert resp.status_code == 200
    data = resp.json()
    assert "direct_competitors" in data
    assert "same_target" in data
    assert "clinical_stage_competitors" in data
    assert "approved_standards_of_care" in data
    assert "emerging_academic_programs" in data


def test_api_get_head_to_head_comparison(client: TestClient) -> None:
    resp = client.get("/api/v1/competitive/asset/zongertinib/head-to-head/tdxd")
    assert resp.status_code == 200
    data = resp.json()
    assert data["competitor_id"] == "tdxd"
    assert "potency" in data
    assert "selectivity" in data
    assert "cns" in data
    assert "safety" in data
    assert "efficacy" in data
    assert "ownership" in data
    assert "commercial_opportunity" in data


def test_api_get_white_space_opportunities(client: TestClient) -> None:
    resp = client.get("/api/v1/competitive/asset/zongertinib/white-space")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3


def test_api_evaluate_custom_asset(client: TestClient) -> None:
    payload = {
        "asset_id": "custom-lead-99",
        "asset_name": "Custom Lead 99",
        "target": "HER2",
        "indication": "Colorectal Cancer",
        "patient_population": "HER2-amplified metastatic CRC",
        "modality": "Small Molecule TKI",
        "stage": "Phase I",
    }
    resp = client.post("/api/v1/competitive/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "custom-lead-99"
    assert data["competitive_density"]["density_score"] > 0
    assert data["differentiation"]["differentiation_score"] > 0


def test_api_not_found_handling(client: TestClient) -> None:
    resp = client.get("/api/v1/competitive/asset/nonexistent-compound")
    assert resp.status_code == 404

    resp = client.get("/api/v1/competitive/asset/zongertinib/head-to-head/nonexistent-rival")
    assert resp.status_code == 404
