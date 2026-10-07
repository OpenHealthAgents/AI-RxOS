"""
Unit and Integration Tests for Semantic and Structured Search.

Tests:
1. Natural language query parsing into structured constraints
2. Validation enforcement: "Never use LLM output as the final database query without validation."
3. Rejection of unvalidated fields and SQL injection attempts
4. Asset search
5. Target search
6. Indication search
7. Biomarker search
8. Trial search
9. Publication search
10. Company search
11. Opportunity search
12. API endpoints and schema checks
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.search import (
    ALLOWED_CONSTRAINT_FIELDS,
    NaturalLanguageSearchParser,
    OperatorType,
    ParsedSearchQuery,
    QueryValidationError,
    SearchEngine,
    SearchMode,
    SearchQueryRequest,
    SearchResultItem,
    SearchTargetType,
    SqlCompilerAndValidator,
    StructuredConstraint,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def search_engine() -> SearchEngine:
    return SearchEngine()


# ==============================================================================
# 1. Natural Language Parser Tests
# ==============================================================================

def test_parse_natural_language_to_structured_constraints() -> None:
    """Tests converting a clinical oncology query into structured constraints."""
    query = "Find HER2 mutant-selective TKIs for NSCLC with brain metastases"
    parsed = NaturalLanguageSearchParser.parse(query)

    assert parsed.target_type == SearchTargetType.ASSET
    assert len(parsed.structured_constraints) >= 3

    fields = {c.field: c.value for c in parsed.structured_constraints}
    assert fields.get("target") == "HER2"
    assert "Lung Cancer" in fields.get("disease", "") or "NSCLC" in fields.get("disease", "")
    assert fields.get("modality") == "SMALL_MOLECULE_TKI"
    assert fields.get("cns_active") is True


def test_parse_company_and_licensing_signals() -> None:
    """Tests parsing partner/licensing queries."""
    query = "Boehringer Ingelheim assets available for out-licensing in Phase 2"
    parsed = NaturalLanguageSearchParser.parse(query)

    fields = {c.field: (c.operator, c.value) for c in parsed.structured_constraints}
    assert "Boehringer" in fields.get("company", ("", ""))[1]
    assert fields.get("licensing_status", ("", ""))[1] == "POTENTIALLY_AVAILABLE"
    assert fields.get("stage", ("", ""))[1] == "Phase II"


def test_infer_target_type_from_query() -> None:
    """Verifies that entity targets are automatically inferred from query phrasing."""
    assert NaturalLanguageSearchParser.infer_target_type("Phase 2 clinical trials with tucatinib") == SearchTargetType.TRIAL
    assert NaturalLanguageSearchParser.infer_target_type("PubMed publications on Wilding nature cancer") == SearchTargetType.PUBLICATION
    assert NaturalLanguageSearchParser.infer_target_type("Biopharma companies developing ErbB2 inhibitors") == SearchTargetType.COMPANY
    assert NaturalLanguageSearchParser.infer_target_type("Biomarkers predicting response to HER2 TKIs") == SearchTargetType.BIOMARKER
    assert NaturalLanguageSearchParser.infer_target_type("Biological targets in RTK pathway") == SearchTargetType.TARGET
    assert NaturalLanguageSearchParser.infer_target_type("Licensing deals and opportunities in solid tumors") == SearchTargetType.OPPORTUNITY


# ==============================================================================
# 2. Query Validation & Anti-Injection Tests
# ==============================================================================

def test_validation_rejects_unwhitelisted_constraint_fields() -> None:
    """
    CRITICAL INVARIANT TEST:
    Constraints on arbitrary non-whitelisted columns must be rejected.
    """
    with pytest.raises(ValueError) as exc:
        StructuredConstraint(
            field="unregistered_private_table_col",
            operator=OperatorType.EQUALS,
            value="malicious",
        )
    assert "not recognized or permitted" in str(exc.value)


def test_validation_rejects_sql_injection_in_constraint_values() -> None:
    """
    CRITICAL INVARIANT TEST:
    Never use LLM output as the final database query without validation.
    Detects and rejects SQL injection tokens.
    """
    malicious_constraint = StructuredConstraint(
        field="target",
        operator=OperatorType.EQUALS,
        value="HER2; DROP TABLE canonical.therapeutic_assets; --",
    )

    with pytest.raises(QueryValidationError) as exc:
        SqlCompilerAndValidator.validate_constraint_safety(malicious_constraint)
    assert "Unsafe token detected" in str(exc.value)


def test_sql_compiler_generates_safe_parametric_sql() -> None:
    """Verifies compilation to safe parameterized query with placeholders."""
    query = "Find Phase 2 HER2 inhibitors"
    parsed = NaturalLanguageSearchParser.parse(query)

    compiled = SqlCompilerAndValidator.compile_to_parametric_sql(parsed)
    assert compiled.target_table == "canonical.therapeutic_assets"
    assert "SELECT * FROM canonical.therapeutic_assets" in compiled.sql_template
    assert ":p_target_" in compiled.sql_template
    assert ":p_stage_" in compiled.sql_template
    assert any(k.startswith("p_target_") and v == "HER2" for k, v in compiled.parameters.items())
    assert any(k.startswith("p_stage_") and v == "Phase II" for k, v in compiled.parameters.items())


# ==============================================================================
# 3. Eight Search Targets Execution Tests
# ==============================================================================

def test_asset_search(search_engine: SearchEngine) -> None:
    """1. Asset Search: Matches assets by target, disease, and CNS activity."""
    req = SearchQueryRequest(
        query="HER2 CNS-active breast cancer",
        target_type=SearchTargetType.ASSET,
        mode=SearchMode.HYBRID,
    )
    res = search_engine.search(req)

    assert res.target_type == SearchTargetType.ASSET
    assert res.total_matches >= 1
    # Tucatinib and Zongertinib should match
    titles = [item.title for item in res.items]
    assert any("Tucatinib" in t or "Zongertinib" in t for t in titles)

    item = res.items[0]
    assert len(item.match_reasons) >= 1
    assert item.evidence is not None
    assert item.structured_match is True


def test_target_search(search_engine: SearchEngine) -> None:
    """2. Target Search: Searches biological kinase/receptor targets."""
    req = SearchQueryRequest(
        query="HER2 kinase domain",
        target_type=SearchTargetType.TARGET,
    )
    res = search_engine.search(req)

    assert res.target_type == SearchTargetType.TARGET
    assert res.total_matches >= 1
    assert any("HER2" in item.title for item in res.items)


def test_indication_search(search_engine: SearchEngine) -> None:
    """3. Indication Search: Searches disease and indication nodes."""
    req = SearchQueryRequest(
        query="Non-Small Cell Lung Cancer",
        target_type=SearchTargetType.INDICATION,
    )
    res = search_engine.search(req)

    assert res.target_type == SearchTargetType.INDICATION
    assert res.total_matches >= 1
    assert any("NSCLC" in item.title or "Lung" in item.title for item in res.items)


def test_biomarker_search(search_engine: SearchEngine) -> None:
    """4. Biomarker Search: Searches genomic mutations and diagnostic markers."""
    req = SearchQueryRequest(
        query="Exon 20 insertion",
        target_type=SearchTargetType.BIOMARKER,
    )
    res = search_engine.search(req)

    assert res.target_type == SearchTargetType.BIOMARKER
    assert res.total_matches >= 1
    assert any("Exon 20" in item.title or "EXON20" in item.title for item in res.items)


def test_trial_search(search_engine: SearchEngine) -> None:
    """5. Trial Search: Searches ClinicalTrials.gov studies."""
    req = SearchQueryRequest(
        query="Beamion LUNG-1 NCT04886804",
        target_type=SearchTargetType.TRIAL,
    )
    res = search_engine.search(req)

    assert res.target_type == SearchTargetType.TRIAL
    assert res.total_matches >= 1
    assert any("NCT04886804" in item.title or "Beamion" in item.title for item in res.items)


def test_publication_search(search_engine: SearchEngine) -> None:
    """6. Publication Search: Searches scientific literature / PubMed records."""
    req = SearchQueryRequest(
        query="Wilding Nature Cancer 2024 Zongertinib",
        target_type=SearchTargetType.PUBLICATION,
    )
    res = search_engine.search(req)

    assert res.target_type == SearchTargetType.PUBLICATION
    assert res.total_matches >= 1
    assert any("Nature Cancer" in item.subtitle or "Wilding" in item.title for item in res.items)


def test_company_search(search_engine: SearchEngine) -> None:
    """7. Company Search: Searches biopharma sponsors."""
    req = SearchQueryRequest(
        query="Boehringer Ingelheim",
        target_type=SearchTargetType.COMPANY,
    )
    res = search_engine.search(req)

    assert res.target_type == SearchTargetType.COMPANY
    assert res.total_matches >= 1
    assert any("Boehringer" in item.title for item in res.items)


def test_opportunity_search(search_engine: SearchEngine) -> None:
    """8. Opportunity Search: Searches strategic partnering & pursue opportunities."""
    req = SearchQueryRequest(
        query="HER2 opportunities to PURSUE",
        target_type=SearchTargetType.OPPORTUNITY,
    )
    res = search_engine.search(req)

    assert res.target_type == SearchTargetType.OPPORTUNITY
    assert res.total_matches >= 1
    # Check that highest ranked item incorporates action score
    top = res.items[0]
    assert "Opportunity" in top.title
    assert "PURSUE" in top.subtitle or "PURSUE" in str(top.match_reasons)


# ==============================================================================
# 4. REST API Endpoints Tests
# ==============================================================================

def test_api_search_query(client: TestClient) -> None:
    """Tests POST /api/v1/search/query."""
    payload = {
        "query": "Find Phase 2 HER2 inhibitors",
        "target_type": "asset",
        "mode": "hybrid",
        "limit": 5,
    }
    resp = client.post("/api/v1/search/query", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["target_type"] == "asset"
    assert data["total_matches"] >= 1
    assert data["validated_sql"] is not None
    assert len(data["items"]) >= 1


def test_api_parse_natural_language(client: TestClient) -> None:
    """Tests POST /api/v1/search/parse."""
    resp = client.post("/api/v1/search/parse?query=HER2+brain+metastases+Phase+2")
    assert resp.status_code == 200
    data = resp.json()

    assert data["target_type"] == "asset"
    assert len(data["structured_constraints"]) >= 2
    assert data["is_validated"] is True


def test_api_schema_endpoint(client: TestClient) -> None:
    """Tests GET /api/v1/search/schema."""
    resp = client.get("/api/v1/search/schema")
    assert resp.status_code == 200
    data = resp.json()

    assert "asset" in data["search_targets"]
    assert "opportunity" in data["search_targets"]
    assert "target" in data["allowed_fields"]
    assert "Never use LLM output as the final database query without validation." in data["policy"]


def test_migration_041_exists_and_defines_search_view() -> None:
    """Verifies migration 041 exists with views and audit logging table."""
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "services" / "kg" / "migrations" / "041_semantic_and_structured_search.sql"

    assert migration_path.exists(), f"Migration file not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    assert "view_searchable_assets" in content
    assert "search_query_audit_logs" in content
    assert "validate_search_constraint_safety" in content
    assert "Never use LLM output as the final database query without validation." in content
