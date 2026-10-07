"""
Tests for the Oncology Opportunity Graph and Strict Evidence Provenance.

Validates the 15 canonical relationships:
1.  Asset → Target
2.  Asset → Gene
3.  Asset → Mutation
4.  Asset → Disease
5.  Asset → Biomarker
6.  Asset → Patient Population
7.  Asset → Trial
8.  Asset → Publication
9.  Asset → Company
10. Asset → Competitor
11. Asset → Resistance
12. Asset → Combination
13. Asset → Patent
14. Asset → License
15. Asset → Regulatory Event

Invariant: "Every graph relationship must retain evidence provenance."
"""

from pathlib import Path
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.kg import (
    CANONICAL_ONCOLOGY_RELATIONSHIPS,
    CANONICAL_RELATIONSHIP_CATEGORY_MAP,
    AssetOpportunityGraph,
    EdgeEvidenceProvenance,
    KGEdge,
    KGNode,
    KGNodeType,
    KGRelationshipType,
    MissingEvidenceProvenanceError,
    OncologyKnowledgeGraphEngine,
    RelationshipProvenanceDetail,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def kg_engine() -> OncologyKnowledgeGraphEngine:
    return OncologyKnowledgeGraphEngine()


def test_canonical_fifteen_relationships_specification() -> None:
    """Verifies that all 15 canonical oncology opportunity relationships are defined."""
    assert len(CANONICAL_ONCOLOGY_RELATIONSHIPS) == 15
    expected = [
        "Asset → Target",
        "Asset → Gene",
        "Asset → Mutation",
        "Asset → Disease",
        "Asset → Biomarker",
        "Asset → Patient Population",
        "Asset → Trial",
        "Asset → Publication",
        "Asset → Company",
        "Asset → Competitor",
        "Asset → Resistance",
        "Asset → Combination",
        "Asset → Patent",
        "Asset → License",
        "Asset → Regulatory Event",
    ]
    assert CANONICAL_ONCOLOGY_RELATIONSHIPS == expected
    assert len(CANONICAL_RELATIONSHIP_CATEGORY_MAP) == 15


def test_zongertinib_covers_canonical_opportunity_relationships(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """
    Verifies that Zongertinib has relationships across canonical categories
    with verified evidence provenance on each edge.
    """
    zong_id = UUID("00000000-0000-0000-0000-000000000001")
    opp_graph = kg_engine.get_asset_opportunity_graph(zong_id)

    assert opp_graph.asset_name == "Zongertinib"
    assert opp_graph.total_relationships >= 15
    assert opp_graph.all_relationships_have_provenance is True

    # Check key categories
    cats = opp_graph.relationships_by_category
    assert len(cats["target"]) >= 1
    assert len(cats["gene"]) >= 1
    assert len(cats["mutation"]) >= 1
    assert len(cats["disease"]) >= 1
    assert len(cats["biomarker"]) >= 1
    assert len(cats["patient_population"]) >= 1
    assert len(cats["trial"]) >= 1
    assert len(cats["publication"]) >= 1
    assert len(cats["company"]) >= 1
    assert len(cats["competitor"]) >= 1
    assert len(cats["resistance"]) >= 1
    assert len(cats["combination"]) >= 1
    assert len(cats["patent"]) >= 1
    assert len(cats["license"]) >= 1
    assert len(cats["regulatory_event"]) >= 1

    # Verify provenance on every relationship
    for cat_name, details in cats.items():
        for d in details:
            assert len(d.evidence_lineage) >= 1
            ev = d.evidence_lineage[0]
            assert ev.evidence_id is not None
            assert len(ev.source_citation) > 0
            assert 0.0 <= ev.confidence <= 1.0


def test_tucatinib_covers_canonical_opportunity_relationships(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Tucatinib covers canonical opportunity relationships with provenance."""
    tuc_id = UUID("11111111-1111-1111-1111-111111111111")
    opp_graph = kg_engine.get_asset_opportunity_graph(tuc_id)

    assert opp_graph.asset_name == "Tucatinib"
    assert opp_graph.all_relationships_have_provenance is True

    cats = opp_graph.relationships_by_category
    assert len(cats["target"]) >= 1
    assert len(cats["disease"]) >= 1
    assert len(cats["trial"]) >= 1
    assert len(cats["competitor"]) >= 1
    assert len(cats["combination"]) >= 1
    assert len(cats["patent"]) >= 1
    assert len(cats["license"]) >= 1
    assert len(cats["regulatory_event"]) >= 1


def test_poziotinib_covers_canonical_opportunity_relationships(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Poziotinib covers canonical opportunity relationships with provenance."""
    pozi_id = UUID("33333333-3333-3333-3333-333333333333")
    opp_graph = kg_engine.get_asset_opportunity_graph(pozi_id)

    assert opp_graph.asset_name == "Poziotinib"
    assert opp_graph.all_relationships_have_provenance is True

    cats = opp_graph.relationships_by_category
    assert len(cats["target"]) >= 1
    assert len(cats["mutation"]) >= 1
    assert len(cats["trial"]) >= 1
    assert len(cats["license"]) >= 1
    assert len(cats["regulatory_event"]) >= 1
    assert len(cats["patent"]) >= 1


def test_strict_provenance_enforcement_rejects_empty_evidence(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """
    CRITICAL INVARIANT TEST:
    Adding an edge without evidence MUST raise MissingEvidenceProvenanceError when strict_provenance=True.
    """
    zong_id = UUID("00000000-0000-0000-0000-000000000001")
    fake_node = kg_engine.add_node(
        KGNodeType.TARGET,
        "TARGET:TEST_DUMMY",
        "Dummy Target",
        "Dummy Target for test",
        {},
    )

    # Attempting to add an edge with empty evidence must fail
    with pytest.raises(MissingEvidenceProvenanceError) as exc_info:
        kg_engine.add_edge(
            source_node_id=zong_id,
            relationship_type=KGRelationshipType.TARGETS,
            target_node_id=fake_node.id,
            confidence=1.0,
            properties={},
            evidence=[],  # NO EVIDENCE
            strict_provenance=True,
        )

    assert "TARGETS" in str(exc_info.value)
    assert "must retain evidence provenance" in str(exc_info.value)


def test_graph_wide_provenance_audit(kg_engine: OncologyKnowledgeGraphEngine) -> None:
    """Verifies that 100% of relationships across the entire graph retain provenance."""
    is_valid, total_edges, invalid_edges = kg_engine.validate_all_graph_relationships_have_provenance()
    assert is_valid is True
    assert total_edges > 20
    assert len(invalid_edges) == 0

    audit = kg_engine.get_provenance_audit_summary()
    assert audit["provenance_compliance_pct"] == 100.0
    assert audit["all_relationships_have_provenance"] is True
    assert audit["invalid_edge_count"] == 0
    assert "LITERATURE" in audit["evidence_distribution"]


def test_api_opportunity_graph_endpoints(client: TestClient) -> None:
    """Tests the FastAPI routes for Oncology Opportunity Graph and provenance."""
    zong_id = "00000000-0000-0000-0000-000000000001"

    # 1. Canonical relationship list
    resp_canon = client.get("/api/v1/kg/relationships/canonical")
    assert resp_canon.status_code == 200
    canon_list = resp_canon.json()
    assert len(canon_list) == 15
    assert "Asset → Target" in canon_list
    assert "Asset → Regulatory Event" in canon_list

    # 2. Asset opportunity graph
    resp_graph = client.get(f"/api/v1/kg/assets/{zong_id}/opportunity-graph")
    assert resp_graph.status_code == 200
    graph_data = resp_graph.json()
    assert graph_data["asset_name"] == "Zongertinib"
    assert graph_data["all_relationships_have_provenance"] is True
    assert "target" in graph_data["relationships_by_category"]
    assert "regulatory_event" in graph_data["relationships_by_category"]

    # 3. Query specific category
    resp_targets = client.get(f"/api/v1/kg/assets/{zong_id}/relationships/target")
    assert resp_targets.status_code == 200
    targets = resp_targets.json()
    assert len(targets) >= 1
    assert targets[0]["relationship_category"] == "Asset → Target"
    assert len(targets[0]["evidence_lineage"]) >= 1

    # 4. Provenance audit
    resp_audit = client.get("/api/v1/kg/provenance/audit")
    assert resp_audit.status_code == 200
    audit_data = resp_audit.json()
    assert audit_data["all_relationships_have_provenance"] is True
    assert audit_data["provenance_compliance_pct"] == 100.0

    # 5. Adding edge without evidence should return 422 Unprocessable Entity
    dummy_payload = {
        "source_node_id": zong_id,
        "relationship_type": "TARGETS",
        "target_node_id": "00000000-0000-0000-0000-000000000001",
        "evidence_lineage": [],  # VIOLATION
        "confidence": 1.0,
    }
    resp_edge_fail = client.post("/api/v1/kg/edges", json=dummy_payload)
    assert resp_edge_fail.status_code == 422
    assert "must retain evidence provenance" in resp_edge_fail.json()["detail"]


def test_migration_040_exists_and_defines_opportunity_graph_views() -> None:
    """Verifies migration 040 is created with audit views and trigger."""
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "services" / "kg" / "migrations" / "040_oncology_opportunity_graph_provenance.sql"

    assert migration_path.exists(), f"Migration not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    assert "view_asset_opportunity_graph_edges" in content
    assert "view_asset_canonical_opportunity_summary" in content
    assert "check_edge_has_provenance" in content
    assert "trg_audit_kg_edge_provenance" in content
    assert "Asset → Target" in content
    assert "Asset → Regulatory Event" in content

