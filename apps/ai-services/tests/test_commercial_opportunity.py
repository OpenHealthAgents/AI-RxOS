from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.opportunity_engine.commercial.engine import CommercialOpportunityEngine
from app.opportunity_engine.commercial.models import (
    AssumptionProvenance,
    CommercialAssumptionRecord,
    CommercialOpportunityProfile,
    CommercialUnmetNeedTier,
    CompetitivePressureTier,
    MarketAttractivenessTier,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def engine() -> CommercialOpportunityEngine:
    return CommercialOpportunityEngine()


# ==============================================================================
# 1. Benchmark Loading & Profile Completeness
# ==============================================================================

def test_benchmark_profiles_loaded(engine: CommercialOpportunityEngine) -> None:
    benchmarks = engine.list_benchmark_profiles()
    assert len(benchmarks) >= 5
    asset_ids = {b.asset_id for b in benchmarks}
    assert "zongertinib" in asset_ids
    assert "tucatinib" in asset_ids
    assert "neratinib" in asset_ids
    assert "poziotinib" in asset_ids
    assert "ox-her2-01" in asset_ids


# ==============================================================================
# 2. Eleven Evaluated Dimensions for Zongertinib
# ==============================================================================

def test_zongertinib_eleven_commercial_dimensions(engine: CommercialOpportunityEngine) -> None:
    profile = engine.get_commercial_profile("zongertinib")
    assert profile is not None

    # 1. Addressable Population
    addr = profile.addressable_population
    assert addr.annual_incidence_us == 238000
    assert addr.annual_incidence_eu5 == 185000
    assert addr.annual_incidence_jp == 85000
    assert addr.total_metastatic_pool > 200000
    assert addr.provenance == AssumptionProvenance.EXTERNALLY_SOURCED

    # 2. Biomarker-Defined Population
    bio = profile.biomarker_defined_population
    assert "HER2" in bio.biomarker_name
    assert bio.biomarker_prevalence_pct == 3.0
    assert bio.testing_penetration_rate_pct == 82.0
    assert bio.target_eligible_patient_pool > 5000
    assert bio.provenance == AssumptionProvenance.MODELED

    # 3. Treatment Duration
    tx = profile.treatment_duration
    assert tx.median_pfs_months == 13.8
    assert tx.median_duration_of_treatment_months == 11.2
    assert tx.compliance_persistence_rate_pct >= 85.0
    assert tx.provenance == AssumptionProvenance.OBSERVED

    # 4. Standard of Care
    soc = profile.standard_of_care
    assert "Trastuzumab Deruxtecan" in soc.soc_regimen_name
    assert len(soc.soc_shortcomings) >= 3
    assert any("ILD" in s for s in soc.soc_shortcomings)
    assert soc.provenance == AssumptionProvenance.OBSERVED

    # 5. Unmet Need
    unmet = profile.unmet_need
    assert unmet.unmet_need_score >= 80.0
    assert unmet.unmet_need_tier == CommercialUnmetNeedTier.HIGH
    assert len(unmet.drivers) >= 2

    # 6. Competitive Density
    comp = profile.competitive_density
    assert comp.density_score == 65.0
    assert comp.active_commercial_competitors_count == 1

    # 7. Clinical Differentiation
    diff = profile.clinical_differentiation
    assert diff.differentiation_score >= 85.0
    assert any("59" in d for d in diff.key_differentiators)

    # 8. Potential Line of Therapy
    line = profile.potential_line_of_therapy_eval
    assert "2L" in line.initial_target_line
    assert "1L" in line.potential_expansion_line

    # 9. Pricing Analogs
    pricing = profile.pricing_analogs
    assert pricing.monthly_wac_usd == 21500.0
    assert pricing.gross_to_net_discount_pct == 18.0
    assert pricing.net_realized_monthly_usd == 21500.0 * 0.82

    # 10. Pipeline Crowding
    pipe = profile.pipeline_crowding
    assert pipe.phase_3_threats_count == 1
    assert "DESTINY" in pipe.threat_assessment or "Bay" in pipe.threat_assessment

    # 11. Market Expansion Opportunity
    assert len(profile.market_expansion_opportunities) >= 2
    expansion_names = {e.scenario_name for e in profile.market_expansion_opportunities}
    assert any("Frontline" in n for n in expansion_names)
    assert any("Breast Cancer" in n for n in expansion_names)


# ==============================================================================
# 3. Five Core Produced Outputs
# ==============================================================================

def test_zongertinib_core_produced_outputs(engine: CommercialOpportunityEngine) -> None:
    profile = engine.get_commercial_profile("zongertinib")
    assert profile is not None

    # 1. Commercial Opportunity Score
    assert 80.0 <= profile.commercial_opportunity_score <= 95.0

    # 2. Market Attractiveness
    assert profile.market_attractiveness_tier == MarketAttractivenessTier.HIGH
    assert profile.market_attractiveness_score >= 80.0

    # 3. Competitive Pressure
    assert profile.competitive_pressure_tier == CompetitivePressureTier.MODERATE
    assert 40.0 <= profile.competitive_pressure_score <= 65.0

    # 4. Unmet Need
    assert profile.unmet_need_tier == CommercialUnmetNeedTier.HIGH
    assert profile.unmet_need_score >= 80.0

    # 5. Commercial Confidence
    assert profile.commercial_confidence >= 0.80

    # Modeled Revenue Projections
    rev = profile.modeled_revenue_projections
    assert rev.base_peak_sales_usd > 1_000_000_000.0
    assert rev.bull_peak_sales_usd > rev.base_peak_sales_usd
    assert rev.bear_peak_sales_usd < rev.base_peak_sales_usd


# ==============================================================================
# 4. Strict Epistemic Invariants: Assumption Provenance
# ==============================================================================

def test_assumption_provenance_and_epistemic_audit(engine: CommercialOpportunityEngine) -> None:
    profile = engine.get_commercial_profile("zongertinib")
    assert profile is not None
    assert len(profile.assumptions_audit) >= 4

    provenance_types = {a.provenance for a in profile.assumptions_audit}
    # Zongertinib has Observed, Externally sourced, and Assumed data
    assert AssumptionProvenance.OBSERVED in provenance_types
    assert AssumptionProvenance.EXTERNALLY_SOURCED in provenance_types
    assert AssumptionProvenance.ASSUMED in provenance_types


def test_unknown_assumptions_strictly_cap_commercial_confidence(engine: CommercialOpportunityEngine) -> None:
    profile = engine.get_commercial_profile("ox-her2-01")
    assert profile is not None

    # OX-HER2-01 has UNKNOWN assumptions (human duration and pricing authorization)
    assert profile.has_unknown_assumptions is True
    # Epistemic invariant: confidence cannot exceed 0.40
    assert profile.commercial_confidence <= 0.40
    assert profile.commercial_confidence == 0.35

    # Test that model validator rejects violation of the invariant
    with pytest.raises(ValidationError):
        CommercialOpportunityProfile.model_validate({
            **profile.model_dump(),
            "commercial_confidence": 0.85,
        })


# ==============================================================================
# 5. Benchmark Diversity: Tucatinib, Neratinib, Poziotinib
# ==============================================================================

def test_tucatinib_commercial_benchmark(engine: CommercialOpportunityEngine) -> None:
    profile = engine.get_commercial_profile("tucatinib")
    assert profile is not None
    assert profile.market_attractiveness_tier == MarketAttractivenessTier.VERY_HIGH
    assert profile.commercial_opportunity_score >= 80.0
    assert profile.commercial_confidence >= 0.90
    assert any("Pfizer" in a.source_citation for a in profile.assumptions_audit)


def test_neratinib_commercial_benchmark(engine: CommercialOpportunityEngine) -> None:
    profile = engine.get_commercial_profile("neratinib")
    assert profile is not None
    assert profile.competitive_pressure_tier == CompetitivePressureTier.INTENSE
    assert profile.unmet_need_tier == CommercialUnmetNeedTier.LOW
    assert profile.commercial_opportunity_score < 50.0


def test_poziotinib_commercial_benchmark(engine: CommercialOpportunityEngine) -> None:
    profile = engine.get_commercial_profile("poziotinib")
    assert profile is not None
    assert profile.market_attractiveness_tier == MarketAttractivenessTier.LOW
    assert profile.commercial_opportunity_score < 20.0
    assert profile.competitive_pressure_tier == CompetitivePressureTier.INTENSE


# ==============================================================================
# 6. Dynamic Evaluation for Unmodeled Custom Assets
# ==============================================================================

def test_dynamic_evaluation_for_custom_asset(engine: CommercialOpportunityEngine) -> None:
    profile = engine.evaluate_commercial_opportunity(
        asset_id="novel-crc-lead",
        asset_name="Novel CRC Lead",
        target="HER2",
        indication="Colorectal Cancer",
        potential_line_of_therapy="3L+ refractory mCRC",
    )
    assert profile.asset_id == "novel-crc-lead"
    assert profile.asset_name == "Novel CRC Lead"
    assert profile.indication == "Colorectal Cancer"
    assert profile.commercial_opportunity_score > 0.0
    assert profile.has_unknown_assumptions is True
    # Invariant: dynamically created early assets with unknown duration have capped confidence
    assert profile.commercial_confidence <= 0.40
    assert profile.modeled_revenue_projections.base_peak_sales_usd > 0.0


# ==============================================================================
# 7. FastAPI HTTP Endpoints
# ==============================================================================

def test_api_list_commercial_benchmarks(client: TestClient) -> None:
    resp = client.get("/api/v1/commercial/benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 5


def test_api_get_asset_commercial_profile(client: TestClient) -> None:
    resp = client.get("/api/v1/commercial/asset/zongertinib")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "zongertinib"
    assert "commercial_opportunity_score" in data
    assert "market_attractiveness_tier" in data
    assert "competitive_pressure_tier" in data
    assert "unmet_need_tier" in data
    assert "commercial_confidence" in data
    assert "addressable_population" in data
    assert "biomarker_defined_population" in data
    assert "modeled_revenue_projections" in data


def test_api_get_asset_commercial_assumptions(client: TestClient) -> None:
    resp = client.get("/api/v1/commercial/asset/zongertinib/assumptions")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 4
    for a in data:
        assert a["provenance"] in [
            "Observed", "Externally sourced", "Modeled", "Assumed", "Unknown"
        ]


def test_api_get_asset_revenue_projections(client: TestClient) -> None:
    resp = client.get("/api/v1/commercial/asset/zongertinib/projections")
    assert resp.status_code == 200
    data = resp.json()
    assert data["base_peak_sales_usd"] > 0
    assert data["bull_peak_sales_usd"] > data["base_peak_sales_usd"]
    assert "DerivationLineage" in data or "derivation_lineage" in data


def test_api_evaluate_custom_asset(client: TestClient) -> None:
    payload = {
        "asset_id": "test-asset-88",
        "asset_name": "Test Asset 88",
        "target": "EGFR",
        "indication": "Glioblastoma",
        "potential_line_of_therapy": "1L Newly Diagnosed GBM",
    }
    resp = client.post("/api/v1/commercial/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "test-asset-88"
    assert data["commercial_opportunity_score"] > 0
    assert data["commercial_confidence"] <= 0.40


def test_api_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/commercial/asset/nonexistent-compound")
    assert resp.status_code == 404
