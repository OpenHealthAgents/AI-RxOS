from pathlib import Path
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.kg import (
    KGNode,
    KGNodeType,
    KGRelationshipType,
    OncologyGraphQueryResult,
    OncologyKnowledgeGraphEngine,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def kg_engine() -> OncologyKnowledgeGraphEngine:
    return OncologyKnowledgeGraphEngine()


def test_kg_represents_all_eighteen_relationships_and_nineteen_node_types(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """
    Verifies that the knowledge graph represents all 19 node types:
    ASSET, TARGET, GENE, MUTATION, PATHWAY, DISEASE, INDICATION, BIOMARKER,
    PATIENT_POPULATION, TRIAL, PUBLICATION, COMPANY, INSTITUTION, COMPETITOR,
    RESISTANCE_MECHANISM, COMBINATION, PATENT, LICENSE, REGULATORY_EVENT.

    And all 18 directed relationships:
    TARGETS, INVOLVES_GENE, HARBORS_MUTATION, MODULATES_PATHWAY, TREATS_DISEASE,
    INDICATED_FOR, STRATIFIED_BY_BIOMARKER, ENROLLS_POPULATION, EVALUATED_IN_TRIAL,
    REPORTED_IN_PUB, DEVELOPED_BY_COMPANY, ORIGINATED_AT_INSTITUTION, COMPETES_WITH,
    ACQUIRES_RESISTANCE, OVERCOMES_RESISTANCE_VIA, COVERED_BY_PATENT,
    SUBJECT_TO_LICENSE, GOVERNED_BY_REGULATORY_EVENT.
    """
    assert len(KGNodeType) == 19
    assert len(KGRelationshipType) == 18

    # Verify nodes present in preloaded oncology graph
    present_node_types = set()
    for node in kg_engine._nodes.values():
        present_node_types.add(node.node_type)

    assert KGNodeType.ASSET in present_node_types
    assert KGNodeType.TARGET in present_node_types
    assert KGNodeType.GENE in present_node_types
    assert KGNodeType.MUTATION in present_node_types
    assert KGNodeType.PATHWAY in present_node_types
    assert KGNodeType.DISEASE in present_node_types
    assert KGNodeType.INDICATION in present_node_types
    assert KGNodeType.BIOMARKER in present_node_types
    assert KGNodeType.PATIENT_POPULATION in present_node_types
    assert KGNodeType.TRIAL in present_node_types
    assert KGNodeType.PUBLICATION in present_node_types
    assert KGNodeType.COMPANY in present_node_types
    assert KGNodeType.INSTITUTION in present_node_types
    assert KGNodeType.RESISTANCE_MECHANISM in present_node_types
    assert KGNodeType.COMBINATION in present_node_types
    assert KGNodeType.PATENT in present_node_types
    assert KGNodeType.LICENSE in present_node_types
    assert KGNodeType.REGULATORY_EVENT in present_node_types

    # Verify relationships present
    present_rel_types = set()
    for edge in kg_engine._edges.values():
        present_rel_types.add(edge.relationship_type)

    assert KGRelationshipType.TARGETS in present_rel_types
    assert KGRelationshipType.INVOLVES_GENE in present_rel_types
    assert KGRelationshipType.HARBORS_MUTATION in present_rel_types
    assert KGRelationshipType.MODULATES_PATHWAY in present_rel_types
    assert KGRelationshipType.TREATS_DISEASE in present_rel_types
    assert KGRelationshipType.INDICATED_FOR in present_rel_types
    assert KGRelationshipType.STRATIFIED_BY_BIOMARKER in present_rel_types
    assert KGRelationshipType.ENROLLS_POPULATION in present_rel_types
    assert KGRelationshipType.EVALUATED_IN_TRIAL in present_rel_types
    assert KGRelationshipType.REPORTED_IN_PUB in present_rel_types
    assert KGRelationshipType.DEVELOPED_BY_COMPANY in present_rel_types
    assert KGRelationshipType.ORIGINATED_AT_INSTITUTION in present_rel_types
    assert KGRelationshipType.COMPETES_WITH in present_rel_types
    assert KGRelationshipType.ACQUIRES_RESISTANCE in present_rel_types
    assert KGRelationshipType.OVERCOMES_RESISTANCE_VIA in present_rel_types
    assert KGRelationshipType.COVERED_BY_PATENT in present_rel_types
    assert KGRelationshipType.SUBJECT_TO_LICENSE in present_rel_types
    assert KGRelationshipType.GOVERNED_BY_REGULATORY_EVENT in present_rel_types


def test_question_1_what_assets_target_her2(kg_engine: OncologyKnowledgeGraphEngine) -> None:
    """Verifies Q1: What assets target HER2?"""
    result = kg_engine.answer_question_1_assets_targeting_her2()
    assert result.question_id == 1
    assert result.matched_assets_count >= 4

    asset_names = {m.asset_name for m in result.matches}
    assert "Zongertinib" in asset_names
    assert "Tucatinib" in asset_names
    assert "Poziotinib" in asset_names
    assert "Neratinib" in asset_names

    # Verify evidence lineage on match
    zong_match = next(m for m in result.matches if m.asset_name == "Zongertinib")
    assert len(zong_match.evidence_lineage) >= 1
    assert "Nature Cancer" in zong_match.evidence_lineage[0].source_citation


def test_question_2_which_her2_assets_are_cns_active(kg_engine: OncologyKnowledgeGraphEngine) -> None:
    """Verifies Q2: Which HER2 assets are CNS-active?"""
    result = kg_engine.answer_question_2_her2_cns_active_assets()
    assert result.question_id == 2
    assert result.matched_assets_count >= 2

    cns_asset_names = {m.asset_name for m in result.matches}
    assert "Tucatinib" in cns_asset_names
    assert "Zongertinib" in cns_asset_names
    # Poziotinib has poor CNS penetration, should NOT be in primary CNS matches
    assert "Poziotinib" not in cns_asset_names

    tuc_match = next(m for m in result.matches if m.asset_name == "Tucatinib")
    assert "intracranial" in tuc_match.explanation.lower()


def test_question_3_which_assets_target_her2_mutations_rather_than_amplification(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Q3: Which assets target HER2 mutations rather than amplification?"""
    result = kg_engine.answer_question_3_her2_mutations_vs_amplification()
    assert result.question_id == 3
    assert result.matched_assets_count >= 2

    mutant_selective_names = {m.asset_name for m in result.matches}
    assert "Zongertinib" in mutant_selective_names
    assert "Poziotinib" in mutant_selective_names
    # Tucatinib is optimized for amplification/overexpression, not mutant-selective
    assert "Tucatinib" not in mutant_selective_names

    zong_match = next(m for m in result.matches if m.asset_name == "Zongertinib")
    assert "mutant-selective" in zong_match.explanation.lower()


def test_question_4_which_assets_have_phase_1_2_clinical_evidence(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Q4: Which assets have Phase I/II clinical evidence?"""
    result = kg_engine.answer_question_4_phase_1_2_clinical_evidence()
    assert result.question_id == 4
    assert result.matched_assets_count >= 3

    trial_asset_names = {m.asset_name for m in result.matches}
    assert "Zongertinib" in trial_asset_names
    assert "Tucatinib" in trial_asset_names
    assert "Poziotinib" in trial_asset_names


def test_question_5_which_assets_have_biomarker_defined_populations(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Q5: Which assets have biomarker-defined populations?"""
    result = kg_engine.answer_question_5_biomarker_defined_populations()
    assert result.question_id == 5
    assert result.matched_assets_count >= 3

    bio_asset_names = {m.asset_name for m in result.matches}
    assert "Zongertinib" in bio_asset_names
    assert "Poziotinib" in bio_asset_names
    assert "Tucatinib" in bio_asset_names

    zong_match = next(m for m in result.matches if m.asset_name == "Zongertinib")
    assert any("Exon 20" in n.name or "L755S" in n.name for n in zong_match.matched_nodes)


def test_question_6_which_assets_have_known_resistance_mechanisms(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Q6: Which assets have known resistance mechanisms?"""
    result = kg_engine.answer_question_6_known_resistance_mechanisms()
    assert result.question_id == 6
    assert result.matched_assets_count >= 1

    res_asset_names = {m.asset_name for m in result.matches}
    assert "Zongertinib" in res_asset_names

    zong_match = next(m for m in result.matches if m.asset_name == "Zongertinib")
    assert any("ER Pathway" in n.name for n in zong_match.matched_nodes)


def test_question_7_which_combinations_address_those_mechanisms(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Q7: Which combinations address those mechanisms?"""
    result = kg_engine.answer_question_7_combinations_addressing_resistance()
    assert result.question_id == 7
    assert result.matched_assets_count >= 1

    zong_match = next((m for m in result.matches if m.asset_name == "Zongertinib"), None)
    assert zong_match is not None
    assert any("Fulvestrant" in n.name for n in zong_match.matched_nodes)


def test_question_8_which_assets_have_licensing_signals(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Q8: Which assets have licensing signals?"""
    result = kg_engine.answer_question_8_assets_with_licensing_signals()
    assert result.question_id == 8
    assert result.matched_assets_count >= 1

    lic_asset_names = {m.asset_name for m in result.matches}
    assert "Poziotinib" in lic_asset_names


def test_question_9_which_academic_programs_have_commercial_potential(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Q9: Which academic programs have commercial potential?"""
    result = kg_engine.answer_question_9_academic_programs_with_commercial_potential()
    assert result.question_id == 9
    assert result.matched_assets_count >= 1

    academic_asset_names = {m.asset_name for m in result.matches}
    assert "Zongertinib" in academic_asset_names


def test_question_10_which_assets_compete_in_same_population(
    kg_engine: OncologyKnowledgeGraphEngine,
) -> None:
    """Verifies Q10: Which assets compete in the same population?"""
    result = kg_engine.answer_question_10_competitors_in_same_population()
    assert result.question_id == 10
    assert result.matched_assets_count >= 2

    # Check Zongertinib vs Poziotinib competition in NSCLC
    lung_comp = next(
        (m for m in result.matches if "Zongertinib" in m.asset_name or "Poziotinib" in m.asset_name),
        None,
    )
    assert lung_comp is not None

    # Check Tucatinib vs Neratinib competition in breast cancer
    breast_comp = next(
        (m for m in result.matches if "Tucatinib" in m.asset_name or "Neratinib" in m.asset_name),
        None,
    )
    assert breast_comp is not None


def test_graph_lineage_back_to_evidence(kg_engine: OncologyKnowledgeGraphEngine) -> None:
    """
    Verifies that every matched path in graph results retains full lineage back to evidence:
    - Evidence ID
    - Evidence type (LITERATURE, CLINICAL_TRIAL, etc.)
    - Citation string
    - Confidence score
    """
    q1 = kg_engine.answer_question_1_assets_targeting_her2()
    for match in q1.matches:
        assert len(match.evidence_lineage) >= 1
        ev = match.evidence_lineage[0]
        assert ev.evidence_id is not None
        assert ev.evidence_type in ("LITERATURE", "CLINICAL_TRIAL", "REGULATORY_RECORD", "PATENT")
        assert len(ev.source_citation) > 0
        assert 0.0 <= ev.confidence <= 1.0


def test_fastapi_kg_endpoints(client: TestClient) -> None:
    """
    Verifies FastAPI knowledge graph endpoints:
    - GET /api/v1/kg/questions
    - GET /api/v1/kg/questions/{id}
    - GET /api/v1/kg/nodes/{id}
    """
    # 1. List questions
    resp_list = client.get("/api/v1/kg/questions")
    assert resp_list.status_code == 200
    questions = resp_list.json()
    assert len(questions) == 10
    assert questions[0]["text"] == "What assets target HER2?"

    # 2. Execute question 1
    resp_q1 = client.get("/api/v1/kg/questions/1")
    assert resp_q1.status_code == 200
    q1_data = resp_q1.json()
    assert q1_data["question_id"] == 1
    assert q1_data["matched_assets_count"] >= 4

    # 3. Execute question 2 (CNS)
    resp_q2 = client.get("/api/v1/kg/questions/2")
    assert resp_q2.status_code == 200
    q2_data = resp_q2.json()
    assert q2_data["question_id"] == 2
    assert any("Tucatinib" in m["asset_name"] for m in q2_data["matches"])


def test_migration_020_exists_and_defines_all_tables() -> None:
    """
    Verifies that services/kg/migrations/020_oncology_knowledge_graph.sql
    exists and defines kg_nodes, kg_edges, and kg_edge_evidence.
    """
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "services" / "kg" / "migrations" / "020_oncology_knowledge_graph.sql"

    assert migration_path.exists(), f"Migration file not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    # Tables
    assert "CREATE TABLE IF NOT EXISTS kg_nodes" in content
    assert "CREATE TABLE IF NOT EXISTS kg_edges" in content
    assert "CREATE TABLE IF NOT EXISTS kg_edge_evidence" in content

    # Node types
    assert "'ASSET'" in content
    assert "'TARGET'" in content
    assert "'MUTATION'" in content
    assert "'PATIENT_POPULATION'" in content
    assert "'RESISTANCE_MECHANISM'" in content
    assert "'COMBINATION'" in content

    # Edge relationship types
    assert "'TARGETS'" in content
    assert "'HARBORS_MUTATION'" in content
    assert "'ACQUIRES_RESISTANCE'" in content
    assert "'OVERCOMES_RESISTANCE_VIA'" in content
    assert "'COMPETES_WITH'" in content
