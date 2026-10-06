from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.discover import (
    DiscoverEngine,
    DiscoverQueryRequest,
    DiscoverQueryResult,
    NaturalLanguageQueryParser,
    RankedDiscoverMatch,
    StructuredDiscoverFilters,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def discover_engine() -> DiscoverEngine:
    return DiscoverEngine()


# ==============================================================================
# 1. Database Migration & Schema Verification
# ==============================================================================

def test_migration_021_discover_audit_ddl_exists() -> None:
    """
    Validates that the discover query audit migration file exists and defines
    the audit table, indexes, and full-text search index.
    """
    migration_file = Path("services/kg/migrations/021_discover_engine_audit.sql")
    assert migration_file.exists(), "Migration 021_discover_engine_audit.sql must exist"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS discover_queries_audit" in content
    assert "natural_language_query TEXT NOT NULL" in content
    assert "parsed_filters JSONB NOT NULL DEFAULT '{}'::jsonb" in content
    assert "idx_discover_audit_created" in content
    assert "idx_discover_audit_query" in content


# ==============================================================================
# 2. 14-Dimensional Structured Natural Language Parsing
# ==============================================================================

def test_natural_language_parser_all_fourteen_dimensions() -> None:
    """
    Verifies that the NaturalLanguageQueryParser extracts all 14 structured dimensions:
    1. target
    2. disease
    3. indication
    4. stage
    5. modality
    6. biomarker
    7. mutation
    8. cns_requirement
    9. clinical_evidence
    10. safety
    11. competition
    12. ownership
    13. licensing
    14. commercial_opportunity
    """
    complex_query = (
        "Find early-stage small molecule kinase inhibitor targeting HER2 with L755S mutation "
        "in breast cancer with CNS brain penetration, clinical evidence in patients, "
        "high selectivity sparing wild-type, limited competition, academic origin, "
        "available for licensing with high commercial potential."
    )

    filters = NaturalLanguageQueryParser.parse(complex_query)

    # 1. Target
    assert filters.target == "HER2"
    # 2. Disease
    assert filters.disease == "Breast Cancer"
    # 3. Indication
    assert filters.indication is not None
    # 4. Stage
    assert "PRECLINICAL" in filters.stage or "PHASE_I" in filters.stage
    # 5. Modality
    assert filters.modality == "SMALL_MOLECULE_TKI"
    # 6. Biomarker
    assert filters.biomarker is not None
    # 7. Mutation
    assert filters.mutation == "L755S"
    # 8. CNS Requirement
    assert filters.cns_requirement is True
    # 9. Clinical Evidence
    assert filters.clinical_evidence is True
    # 10. Safety
    assert filters.safety is not None
    # 11. Competition
    assert filters.competition is not None
    # 12. Ownership
    assert filters.ownership is not None
    # 13. Licensing
    assert filters.licensing == "POTENTIALLY_AVAILABLE"
    # 14. Commercial Opportunity
    assert filters.commercial_opportunity is not None


# ==============================================================================
# 3. Five Archetype User Queries & Strict Output Contracts
# ==============================================================================

def test_archetype_query_1_early_stage_her2_with_cns(discover_engine: DiscoverEngine) -> None:
    """
    Query 1: 'Find early-stage HER2 assets with CNS activity.'
    Must parse target, stage, and CNS requirement; return ranked assets
    exposing ranking, reason, evidence, confidence, and unknowns.
    """
    query = "Find early-stage HER2 assets with CNS activity."
    result = discover_engine.discover(query)

    assert result.parsed_filters.target == "HER2"
    assert "PRECLINICAL" in result.parsed_filters.stage or "PHASE_II" in result.parsed_filters.stage
    assert result.parsed_filters.cns_requirement is True
    assert result.results_count > 0

    # Ensure top candidate is CNS-penetrant HER2 asset (Zongertinib or OX-HER2-01)
    top_match = result.ranked_assets[0]
    assert top_match.ranking == 1
    assert top_match.asset_id in ("zongertinib", "ox-her2-01", "tucatinib")
    assert "CNS" in top_match.reason or "brain" in top_match.reason.lower()

    # Strict contract assertions
    assert top_match.ranking > 0
    assert len(top_match.reason) > 0
    assert len(top_match.evidence) > 0
    assert 0.0 <= top_match.confidence <= 1.0
    assert isinstance(top_match.unknowns, list)


def test_archetype_query_2_selective_her2_mutant_with_clinical_evidence(discover_engine: DiscoverEngine) -> None:
    """
    Query 2: 'Find selective HER2-mutant inhibitors with clinical evidence.'
    """
    query = "Find selective HER2-mutant inhibitors with clinical evidence."
    result = discover_engine.discover(query)

    assert result.parsed_filters.target == "HER2"
    assert result.parsed_filters.biomarker is not None
    assert result.parsed_filters.clinical_evidence is True
    assert result.parsed_filters.safety is not None
    assert result.results_count > 0

    # Top match should be Zongertinib due to high mutant selectivity and proven clinical evidence
    top_match = result.ranked_assets[0]
    assert top_match.asset_id == "zongertinib"
    assert "selectivity" in top_match.reason.lower() or "clinical response" in top_match.reason.lower()
    assert top_match.match_score >= 80.0


def test_archetype_query_3_preclinical_brain_penetration_limited_competition(discover_engine: DiscoverEngine) -> None:
    """
    Query 3: 'Find preclinical oncology assets with strong brain penetration and limited competition.'
    """
    query = "Find preclinical oncology assets with strong brain penetration and limited competition."
    result = discover_engine.discover(query)

    assert "PRECLINICAL" in result.parsed_filters.stage
    assert result.parsed_filters.cns_requirement is True
    assert result.parsed_filters.competition is not None
    assert result.results_count > 0

    # Top match should be OX-HER2-01 (preclinical with brain penetration)
    top_match = result.ranked_assets[0]
    assert top_match.asset_id == "ox-her2-01"
    assert top_match.stage == "PRECLINICAL"
    assert "brain" in top_match.reason.lower() or "cns" in top_match.reason.lower()


def test_archetype_query_4_assets_available_for_licensing(discover_engine: DiscoverEngine) -> None:
    """
    Query 4: 'Find assets potentially available for licensing.'
    """
    query = "Find assets potentially available for licensing."
    result = discover_engine.discover(query)

    assert result.parsed_filters.licensing == "POTENTIALLY_AVAILABLE"
    assert result.results_count > 0

    # Top matches should be assets with licensing availability (e.g. OX-HER2-01 or Poziotinib)
    available_ids = {"ox-her2-01", "poziotinib"}
    assert result.ranked_assets[0].asset_id in available_ids
    assert "licensing" in result.ranked_assets[0].reason.lower()


def test_archetype_query_5_academic_programs_translational_potential(discover_engine: DiscoverEngine) -> None:
    """
    Query 5: 'Find academic oncology programs with translational potential.'
    """
    query = "Find academic oncology programs with translational potential."
    result = discover_engine.discover(query)

    assert result.parsed_filters.ownership == "Academic / Translational origin"
    assert result.parsed_filters.commercial_opportunity is not None
    assert result.results_count > 0

    # Top match should have academic origin
    top_match = result.ranked_assets[0]
    assert top_match.asset_id in ("ox-her2-01", "zongertinib")
    assert "academic" in top_match.reason.lower() or "translational" in top_match.reason.lower()


# ==============================================================================
# 4. Invariant Verification: Every Result Exposes All Required Fields
# ==============================================================================

def test_every_result_strictly_exposes_required_fields(discover_engine: DiscoverEngine) -> None:
    """
    Guarantees the strict requirement:
    'Every result must expose: ranking, reason, evidence, confidence, unknowns.'
    """
    test_queries = [
        "Find early-stage HER2 assets with CNS activity.",
        "Find selective HER2-mutant inhibitors with clinical evidence.",
        "Find preclinical oncology assets with strong brain penetration and limited competition.",
        "Find assets potentially available for licensing.",
        "Find academic oncology programs with translational potential.",
    ]

    for q in test_queries:
        res = discover_engine.discover(q)
        assert len(res.ranked_assets) > 0, f"Query '{q}' returned no results"

        for idx, match in enumerate(res.ranked_assets, start=1):
            # 1. ranking (1-based, matches list position)
            assert match.ranking == idx
            assert isinstance(match.ranking, int)
            assert match.ranking >= 1

            # 2. reason
            assert isinstance(match.reason, str)
            assert len(match.reason.strip()) > 0

            # 3. evidence
            assert isinstance(match.evidence, list)
            assert len(match.evidence) > 0
            for ev in match.evidence:
                assert "citation" in ev or "source" in ev

            # 4. confidence
            assert isinstance(match.confidence, float)
            assert 0.0 <= match.confidence <= 1.0

            # 5. unknowns
            assert isinstance(match.unknowns, list)
            assert len(match.unknowns) > 0
            for unk in match.unknowns:
                assert isinstance(unk, str)
                assert len(unk.strip()) > 0

            # Score monotonic check
            assert 0.0 <= match.match_score <= 100.0


def test_ranking_is_descending_by_match_score(discover_engine: DiscoverEngine) -> None:
    """
    Verifies candidates are ordered in descending order of match_score.
    """
    query = "Find selective HER2-mutant inhibitors with clinical evidence."
    result = discover_engine.discover(query)

    scores = [asset.match_score for asset in result.ranked_assets]
    assert scores == sorted(scores, reverse=True), "Assets must be ranked descending by match score"


def test_explicit_filters_override_parsed_query(discover_engine: DiscoverEngine) -> None:
    """
    Verifies that explicitly passed StructuredDiscoverFilters override natural language parsing.
    """
    query = "Find early-stage HER2 assets with CNS activity."
    explicit = StructuredDiscoverFilters(
        target="EGFR",
        stage=["PHASE_III"],
    )

    result = discover_engine.discover(query, explicit_filters=explicit)
    assert result.parsed_filters.target == "EGFR"
    assert result.parsed_filters.stage == ["PHASE_III"]
    # CNS requirement was parsed from text and not overridden
    assert result.parsed_filters.cns_requirement is True


# ==============================================================================
# 5. FastAPI Endpoints Integration
# ==============================================================================

def test_api_discover_search(client: TestClient) -> None:
    """
    Tests POST /api/v1/discover/search endpoint.
    """
    payload = {
        "query": "Find early-stage HER2 assets with CNS activity.",
        "top_k": 3,
    }
    resp = client.post("/api/v1/discover/search", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert "query" in data
    assert "parsed_filters" in data
    assert "ranked_assets" in data
    assert len(data["ranked_assets"]) <= 3

    for item in data["ranked_assets"]:
        assert "ranking" in item
        assert "reason" in item
        assert "evidence" in item
        assert "confidence" in item
        assert "unknowns" in item
        assert "match_score" in item


def test_api_discover_parse(client: TestClient) -> None:
    """
    Tests POST /api/v1/discover/parse endpoint.
    """
    resp = client.post(
        "/api/v1/discover/parse",
        params={"query": "Find selective HER2-mutant inhibitors with clinical evidence."},
    )
    assert resp.status_code == 200

    filters = resp.json()
    assert filters["target"] == "HER2"
    assert filters["clinical_evidence"] is True
    assert filters["biomarker"] is not None
    assert filters["safety"] is not None
