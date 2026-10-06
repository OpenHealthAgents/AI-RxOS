from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.cns import (
    CNSEvidenceLevel,
    CNSIntelligenceEngine,
    CNSIntelligenceProfile,
    CNSParameterType,
    CNSSpecies,
    EvaluateAssetCNSRequest,
    EvaluateAssetCNSResponse,
    NormalizedCNSParameter,
    RawCNSObservation,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def cns_engine() -> CNSIntelligenceEngine:
    return CNSIntelligenceEngine()


# ==============================================================================
# 1. Database Migration & Schema Verification
# ==============================================================================

def test_migration_023_cns_intelligence_ddl_exists() -> None:
    """
    Validates that the CNS intelligence migration file exists and defines
    the raw observations and evaluation tables with appropriate indexes.
    """
    migration_file = Path("services/kg/migrations/023_cns_intelligence.sql")
    assert migration_file.exists(), "Migration 023_cns_intelligence.sql must exist"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS cns_raw_observations" in content
    assert "CREATE TABLE IF NOT EXISTS cns_evaluations" in content
    assert "idx_cns_obs_asset" in content
    assert "idx_cns_eval_asset" in content


# ==============================================================================
# 2. Capture All Required Parameters
# ==============================================================================

def test_capture_all_required_cns_parameters(cns_engine: CNSIntelligenceEngine) -> None:
    """
    Verifies capturing of:
    - brain/plasma ratio (Kp)
    - Kp,uu
    - CSF exposure
    - unbound brain concentration (Cu,brain)
    - BBB penetration (efflux ratio)
    - brain tumor exposure
    - intracranial response (iORR)
    - CNS progression (iPFS)
    - brain metastasis response
    """
    profile = cns_engine.get_benchmark_profile("tucatinib")

    captured_types = {p.parameter_type for p in profile.normalized_parameters.values()}
    raw_types = {o.parameter_type for o in profile.raw_observations}

    assert CNSParameterType.BRAIN_PLASMA_RATIO_KP in raw_types
    assert CNSParameterType.KP_UU in raw_types
    assert CNSParameterType.CSF_EXPOSURE in raw_types
    assert CNSParameterType.UNBOUND_BRAIN_CONCENTRATION in raw_types
    assert CNSParameterType.BBB_PENETRATION in raw_types
    assert CNSParameterType.INTRACRANIAL_RESPONSE in raw_types
    assert CNSParameterType.CNS_PROGRESSION in raw_types
    assert CNSParameterType.BRAIN_METASTASIS_RESPONSE in raw_types

    assert len(profile.normalized_parameters) >= 7


# ==============================================================================
# 3. Normalization Across Species and Conditions
# ==============================================================================

def test_normalization_across_species_and_conditions(cns_engine: CNSIntelligenceEngine) -> None:
    """
    Verifies that parameters are normalized across species (Human > NHP > Rodent > In Vitro)
    and experimental conditions.
    """
    profile = cns_engine.get_benchmark_profile("tucatinib")

    kp_param = profile.normalized_parameters.get(CNSParameterType.BRAIN_PLASMA_RATIO_KP.value)
    assert kp_param is not None
    assert kp_param.species == CNSSpecies.HUMAN
    assert kp_param.normalized_value == 0.85
    assert kp_param.normalized_unit == "ratio"

    cu_param = profile.normalized_parameters.get(CNSParameterType.UNBOUND_BRAIN_CONCENTRATION.value)
    assert cu_param is not None
    assert cu_param.normalized_value == 15.4
    assert cu_param.normalized_unit == "nM"


# ==============================================================================
# 4. Distinguish the 5 Evidence Levels
# ==============================================================================

def test_distinguish_five_evidence_levels(cns_engine: CNSIntelligenceEngine) -> None:
    """
    Verifies that the engine explicitly distinguishes all 5 evidentiary tiers:
    1. direct measurement
    2. animal evidence
    3. in vitro inference
    4. mechanistic inference
    5. clinical CNS evidence
    """
    assert len(CNSEvidenceLevel) == 5

    profile = cns_engine.get_benchmark_profile("tucatinib")
    levels = set(profile.evidence_levels_present)

    assert CNSEvidenceLevel.DIRECT_MEASUREMENT in levels
    assert CNSEvidenceLevel.IN_VITRO_INFERENCE in levels
    assert CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE in levels


# ==============================================================================
# 5. Production of the 3 Canonical Scores
# ==============================================================================

def test_produce_three_canonical_scores(cns_engine: CNSIntelligenceEngine) -> None:
    """
    Verifies production of:
    1. CNS Exposure Score (0 - 100)
    2. CNS Activity Score (0 - 100)
    3. CNS Translational Confidence (0.0 - 1.0)
    """
    profile = cns_engine.get_benchmark_profile("tucatinib")

    assert 0.0 <= profile.cns_exposure_score <= 100.0
    assert 0.0 <= profile.cns_activity_score <= 100.0
    assert 0.0 <= profile.cns_translational_confidence <= 1.0

    # Tucatinib is the approved gold standard for HER2+ active brain mets
    assert profile.cns_exposure_score >= 90.0
    assert profile.cns_activity_score >= 85.0
    assert profile.cns_translational_confidence >= 0.90


# ==============================================================================
# 6. Strict Invariant: Never Infer Clinical Efficacy Solely from Physicochemical
# ==============================================================================

def test_never_infer_clinical_cns_efficacy_solely_from_physicochemical(
    cns_engine: CNSIntelligenceEngine,
) -> None:
    """
    CRITICAL RULE:
    Never infer clinical CNS efficacy solely from physicochemical properties.
    If an asset only has in vitro or physicochemical/mechanistic predictions,
    the CNS Activity Score MUST BE 0.0, and a strict warning must be recorded.
    """
    physchem_only_obs = [
        RawCNSObservation(
            asset_id="cpd_physchem_only",
            parameter_type=CNSParameterType.BBB_PENETRATION,
            evidence_level=CNSEvidenceLevel.MECHANISTIC_INFERENCE,
            species=CNSSpecies.IN_VITRO,
            raw_text_value="Favorable physicochemical CNS-MPO score of 5.4, MW 380 Da, cLogP 2.1, TPSA 68 A^2",
            normalized_value=5.4,
            normalized_unit="cns_mpo_score",
            source_citation="In Silico ADME Prediction 2026",
        ),
        RawCNSObservation(
            asset_id="cpd_physchem_only",
            parameter_type=CNSParameterType.BBB_PENETRATION,
            evidence_level=CNSEvidenceLevel.IN_VITRO_INFERENCE,
            species=CNSSpecies.IN_VITRO,
            raw_text_value="High in vitro PAMPA-BBB Papp = 18.2 x 10^-6 cm/s",
            normalized_value=1.5,
            normalized_unit="efflux_ratio",
            source_citation="In Vitro Screening Assay 2026",
        ),
    ]

    profile = cns_engine.evaluate_asset(
        asset_id="cpd_physchem_only",
        asset_name="Physicochemical Lead Compound",
        custom_observations=physchem_only_obs,
    )

    # CNS Activity Score MUST BE 0.0 because no animal or human efficacy data exists!
    assert profile.cns_activity_score == 0.0
    assert profile.clinical_cns_efficacy_inferred_solely_from_physicochemical is False

    # Warning must be explicitly recorded
    warning_found = any(
        "cannot be inferred solely from physicochemical" in u.lower() or "requires animal" in u.lower()
        for u in profile.unknowns
    )
    assert warning_found, "Engine must explicitly warn that clinical CNS efficacy cannot be inferred from physicochemical data"

    # Translational confidence must be capped low (<= 0.35)
    assert profile.cns_translational_confidence <= 0.35


# ==============================================================================
# 7. Lineage and Evidence Provenance
# ==============================================================================

def test_show_evidence_behind_every_score_lineage(cns_engine: CNSIntelligenceEngine) -> None:
    """
    Validates that every score exposes:
    - formula
    - inputs
    - raw observation IDs
    - evidence gaps
    """
    profile = cns_engine.get_benchmark_profile("tucatinib")

    assert "cns_exposure_score" in profile.lineages
    assert "cns_activity_score" in profile.lineages
    assert "cns_translational_confidence" in profile.lineages

    for score_name, lin in profile.lineages.items():
        assert len(lin.formula) > 0
        assert len(lin.inputs) > 0
        assert len(lin.raw_observation_ids) > 0, f"Lineage for '{score_name}' must link to observation IDs"


# ==============================================================================
# 8. Benchmark Profile Differentiations
# ==============================================================================

def test_benchmark_tucatinib_vs_poziotinib(cns_engine: CNSIntelligenceEngine) -> None:
    """
    Compares Tucatinib (CNS-penetrant, Kp,uu=0.48, iORR=47.3%) vs
    Poziotinib (poor penetration, high P-gp/BCRP efflux, iORR<10%).
    """
    tuc = cns_engine.get_benchmark_profile("tucatinib")
    poz = cns_engine.get_benchmark_profile("poziotinib")

    assert tuc.cns_exposure_score >= 90.0
    assert poz.cns_exposure_score <= 20.0

    assert tuc.cns_activity_score >= 85.0
    assert poz.cns_activity_score <= 15.0


def test_benchmark_ox_her2_01_preclinical_distinction(
    cns_engine: CNSIntelligenceEngine,
) -> None:
    """
    OX-HER2-01 is a preclinical asset with high animal brain penetration and TGI,
    but no human clinical trials.
    Verifies that CNS Activity receives animal points (40 pts), but 0 human clinical points.
    """
    ox = cns_engine.get_benchmark_profile("ox-her2-01")

    assert ox.cns_exposure_score >= 90.0
    assert ox.cns_activity_score == 40.0  # Exactly 40 animal points, 0 clinical points
    assert ox.cns_translational_confidence < 0.75  # Capped at preclinical certainty (0.68)

    gaps = ox.lineages["cns_activity_score"].evidence_gaps
    assert any("clinical" in g.lower() or "human" in g.lower() for g in gaps)


# ==============================================================================
# 9. FastAPI Endpoints Integration
# ==============================================================================

def test_api_cns_benchmarks(client: TestClient) -> None:
    resp = client.get("/api/v1/cns/benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    asset_ids = {p["asset_id"] for p in data}
    assert asset_ids == {"tucatinib", "zongertinib", "ox-her2-01", "neratinib", "poziotinib"}


def test_api_cns_profile(client: TestClient) -> None:
    resp = client.get("/api/v1/cns/profile/tucatinib")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "tucatinib"
    assert data["cns_exposure_score"] >= 90.0
    assert "normalized_parameters" in data
    assert "lineages" in data


def test_api_cns_evaluate_custom(client: TestClient) -> None:
    payload = {
        "asset_id": "test_cns_mol",
        "asset_name": "Test CNS Asset",
        "custom_observations": [
            {
                "id": str(uuid4()),
                "asset_id": "test_cns_mol",
                "parameter_type": "kp_uu",
                "evidence_level": "direct_measurement",
                "species": "rat",
                "raw_text_value": "Kp,uu = 0.55",
                "normalized_value": 0.55,
                "normalized_unit": "ratio",
                "source_citation": "Internal PK Study",
                "confidence": 0.95,
            }
        ],
    }
    resp = client.post("/api/v1/cns/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()["profile"]
    assert data["cns_exposure_score"] >= 40.0
    assert data["cns_activity_score"] == 0.0  # Invariant: no animal or clinical efficacy provided!


def test_api_cns_raw_observations(client: TestClient) -> None:
    resp = client.get("/api/v1/cns/observations/tucatinib")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 7
    types = [o["parameter_type"] for o in data]
    assert "kp_uu" in types
    assert "intracranial_response" in types
