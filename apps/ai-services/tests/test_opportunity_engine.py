from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.backtest.engine import HistoricalBacktestEngine
from app.opportunity_engine.comparison.engine import OpportunityComparisonEngine
from app.opportunity_engine.data.fixtures import list_fixture_assets, get_fixture_asset
from app.opportunity_engine.domain.schemas import (
    EvidencePolarity,
    HistoricalBacktestQuery,
    StrategicAction,
)
from app.opportunity_engine.patient_match.engine import PatientMatchEngine, PatientProfileQuery
from app.opportunity_engine.scoring.engine import OpportunityScoringEngine


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_and_get_assets(client: TestClient) -> None:
    # Test GET /api/v1/decision/assets
    resp = client.get("/api/v1/decision/assets")
    assert resp.status_code == 200
    assets = resp.json()
    assert len(assets) >= 4
    asset_ids = [a["id"] for a in assets]
    assert "zongertinib" in asset_ids
    assert "neratinib" in asset_ids

    # Target filter
    resp_her2 = client.get("/api/v1/decision/assets?target=HER2")
    assert resp_her2.status_code == 200
    assert len(resp_her2.json()) >= 4

    # Action filter
    resp_pursue = client.get("/api/v1/decision/assets?action=PURSUE")
    assert resp_pursue.status_code == 200
    pursue_ids = [a["id"] for a in resp_pursue.json()]
    assert "zongertinib" in pursue_ids

    # Test single asset endpoint
    resp_single = client.get("/api/v1/decision/assets/zongertinib")
    assert resp_single.status_code == 200
    zong = resp_single.json()
    assert zong["name"] == "Zongertinib"
    assert zong["owner"] == "Boehringer Ingelheim"
    assert zong["recommendation"]["action"] == "PURSUE"
    assert zong["recommendation"]["development_potential_score"] == 68


def test_evidence_provenance_and_polarity() -> None:
    assets = list_fixture_assets()
    for a in assets:
        # Every asset must have evidence provenance
        all_ev = a.supporting_evidence + a.contradicting_evidence
        assert len(all_ev) > 0 or a.recommendation.action == StrategicAction.AVOID
        for ev in all_ev:
            assert ev.source_ref.startswith(("PMID", "NCT", "FDA", "US-", "AACR"))
            assert ev.as_of_date != ""
            assert ev.polarity in (EvidencePolarity.SUPPORTING, EvidencePolarity.CONTRADICTING)
            assert ev.is_verified is True

    # Check Zongertinib specifically has contradicting evidence regarding resistance
    zong = get_fixture_asset("zongertinib")
    assert zong is not None
    assert len(zong.contradicting_evidence) > 0
    assert "ER and ERBB3" in zong.contradicting_evidence[0].excerpt

    # Check explicit unknowns
    assert len(zong.unknowns) >= 2
    assert any("intracranial" in u.question.lower() for u in zong.unknowns)

    # Check AI inferences labeled
    assert len(zong.ai_inferences) >= 2


def test_scoring_engine_lineage() -> None:
    zong = get_fixture_asset("zongertinib")
    assert zong is not None
    score, tier, lineage = OpportunityScoringEngine.calculate_development_potential(
        zong.biology_profile, zong.safety_profile
    )
    assert score == 68
    assert tier == "High"
    assert lineage["formula"] == "DPS = sum(w_i * metric_i) - safety_penalty"
    assert "target_selectivity" in lineage["components"]

    # Verify stage transition calculation
    transitions = OpportunityScoringEngine.compute_stage_transitions(
        zong.biology_profile, zong.stage
    )
    assert 0.0 < transitions.preclinical_to_ind <= 1.0
    assert 0.0 < transitions.phase_i_to_ii <= 1.0
    assert 0.0 < transitions.phase_ii_to_iii <= 1.0
    assert 0.0 < transitions.phase_iii_to_approval <= 1.0


def test_head_to_head_comparison(client: TestClient) -> None:
    req = {
        "asset_ids": ["zongertinib", "neratinib"],
        "target": "HER2",
        "indication": "Breast Cancer",
        "setting": "Metastatic",
    }
    resp = client.post("/api/v1/decision/compare", json=req)
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["assets"]) == 2
    assert "zongertinib" in data["head_to_head_advantages"]
    assert "neratinib" in data["head_to_head_advantages"]
    assert len(data["key_differentiators"]) >= 3
    assert "Zongertinib" in data["comparison_summary"]


def test_patient_match_engine(client: TestClient) -> None:
    query = {
        "target": "HER2",
        "indication": "Breast Cancer",
        "setting": "Metastatic",
        "mutations": ["HER2 L755S", "HER2 V777L"],
        "hormone_receptor_status": "ER-positive / HER2 non-amplified (IHC 1+)",
        "has_cns_metastases": True,
        "prior_therapies": ["Palbociclib", "Fulvestrant"],
    }
    resp = client.post("/api/v1/decision/patient-match", json=query)
    assert resp.status_code == 200
    res = resp.json()

    assert len(res["matches"]) >= 2
    top_match = res["matches"][0]
    assert top_match["asset_id"] == "zongertinib"
    assert top_match["match_score"] >= 85
    assert top_match["cns_benefit_expected"] is True
    assert "+ Fulvestrant" in top_match["recommended_combination"]
    assert len(top_match["resistance_risks_identified"]) > 0


def test_historical_backtest_anti_leakage(client: TestClient) -> None:
    # Test Neratinib retrospective run as of 2017-06-01 (before FDA approval)
    query = {
        "asset_id": "neratinib",
        "cutoff_date": "2017-06-01",
    }
    resp = client.post("/api/v1/decision/backtest", json=query)
    assert resp.status_code == 200
    result = resp.json()

    assert result["asset_id"] == "neratinib"
    assert result["cutoff_date"] == "2017-06-01"
    assert result["anti_leakage_audit_passed"] is True
    assert result["evidence_items_suppressed_future"] > 0
    assert result["predicted_action_at_cutoff"] == "MONITOR"
    assert result["prediction_accuracy"] == "Calibrated Success"


def test_opportunity_pipeline_matrix(client: TestClient) -> None:
    resp = client.get("/api/v1/decision/opportunities")
    assert resp.status_code == 200
    data = resp.json()
    cats = data["categories"]
    assert len(cats["PURSUE"]) >= 1
    assert len(cats["MONITOR"]) >= 1
    assert len(cats["AVOID"]) >= 1
    assert cats["PURSUE"][0]["name"] == "Zongertinib"
    assert cats["AVOID"][0]["name"] == "Poziotinib"


def test_backtest_poziotinib_negative_prediction(client: TestClient) -> None:
    query = {
        "asset_id": "poziotinib",
        "cutoff_date": "2020-01-01",
    }
    resp = client.post("/api/v1/decision/backtest", json=query)
    assert resp.status_code == 200
    res = resp.json()
    assert res["predicted_action_at_cutoff"] == "AVOID"
    assert res["predicted_development_potential"] == 18
    assert res["prediction_accuracy"] == "True Negative"


def test_tucatinib_cns_profile(client: TestClient) -> None:
    resp = client.get("/api/v1/decision/assets/tucatinib")
    assert resp.status_code == 200
    tuc = resp.json()
    assert tuc["biology_profile"]["cns_potential"] == 92.0
    assert tuc["recommendation"]["action"] == "PARTNER"


def test_regulatory_and_fto_disclaimer_present() -> None:
    assets = list_fixture_assets()
    for a in assets:
        assert "not constitute formal legal opinion" in a.business_profile.fto_legal_disclaimer
