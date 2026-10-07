from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.opportunity_engine.domain.canonical_model import StrategicAction
from app.opportunity_engine.evidence.models import (
    DerivedFeature,
    EvidenceExtraction,
    EvidenceObservation,
    EvidenceSource,
    EvidenceTemporalScope,
    ExtractionMethod,
    ModelOutput,
    SourceType,
)
from app.opportunity_engine.evidence.service import EvidenceService
from app.opportunity_engine.provenance import (
    DecisionInputRecord,
    ModelInputRecord,
    NormalizationRecord,
    ProvenanceGraphEngine,
    ProvenanceIntegrityError,
    ProvenanceNodeType,
    ProvenanceStage,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_provenance_seven_stages_unbroken_traceback():
    """
    Verifies that all 7 stages are explicitly tracked in the provenance graph:
    1. Source
    2. Extraction
    3. Normalization
    4. Feature Derivation
    5. Model Input
    6. Model Output
    7. Decision Input

    Given a final recommendation, it must trace back through all stages to root sources.
    """
    engine = ProvenanceGraphEngine()
    asset_id = uuid4()
    rec_id = uuid4()

    # 1. Source
    src = EvidenceSource(
        source_type=SourceType.PUBLICATION,
        source_id="PMID:38718468",
        title="Selective HER2 oncogenic mutant inhibition by BI 1810631",
        organization="Nature Cancer",
        publication_date=date(2024, 5, 8),
        retrieval_date=date(2024, 5, 10),
        url_reference="https://pubmed.ncbi.nlm.nih.gov/38718468/",
        study_type="in_vitro",
        temporal_validity=EvidenceTemporalScope(
            valid_from=date(2024, 5, 8),
            as_of_date=date(2024, 5, 8),
        ),
    )
    src_node = engine.record_source(src, asset_id)
    assert src_node.stage == ProvenanceStage.SOURCE
    assert len(src_node.content_hash) == 64

    # 2. Extraction
    ext = EvidenceExtraction(
        source_id=src.id,
        source_location="Page 715, Table 1",
        extracted_text="IC50 for HER2 exon 20 insertion mutant is 2.4 nM whereas wild-type EGFR is 142 nM",
        extracted_date=date(2024, 5, 8),
    )
    ext_node = engine.record_extraction(ext, src, asset_id)
    assert ext_node.stage == ProvenanceStage.EXTRACTION
    assert ext_node.parent_hashes == [src_node.content_hash]

    # 3. Normalization
    norm = NormalizationRecord(
        extraction_id=ext.id,
        asset_id=asset_id,
        raw_value="142 nM / 2.4 nM = 59.1-fold selectivity",
        normalized_value=59.1,
        normalized_unit="fold_ratio",
        parameter_name="mutant_vs_wt_selectivity_ratio",
        transformation_rule="ratio_derivation_to_fold",
    )
    norm_node = engine.record_normalization(norm, ext.id)
    assert norm_node.stage == ProvenanceStage.NORMALIZATION
    assert norm_node.parent_hashes == [ext_node.content_hash]

    # 4. Feature Derivation
    feat = DerivedFeature(
        asset_id=asset_id,
        feature_name="target_selectivity_metric",
        computed_value=92.0,
        calculation_formula="min(100, 50 + log10(ratio) * 23.8)",
        source_observation_ids=[norm.id],
    )
    feat_node = engine.record_feature_derivation(feat, [norm.id])
    assert feat_node.stage == ProvenanceStage.FEATURE_DERIVATION
    assert feat_node.parent_hashes == [norm_node.content_hash]

    # 5. Model Input
    model_input = ModelInputRecord(
        model_name="CalibratedMultiAttributeEngine",
        model_version="v0.1",
        asset_id=asset_id,
        feature_ids=[feat.id],
        feature_vector={"target_selectivity": 92.0},
    )
    mi_node = engine.record_model_input(model_input)
    assert mi_node.stage == ProvenanceStage.MODEL_INPUT
    assert mi_node.parent_hashes == [feat_node.content_hash]

    # 6. Model Output
    model_out = ModelOutput(
        asset_id=asset_id,
        model_name="CalibratedMultiAttributeEngine",
        model_version="v0.1",
        output_metric="development_potential_score",
        output_value=74.5,
        derived_feature_ids=[feat.id],
    )
    mo_node = engine.record_model_output(model_out, model_input.id)
    assert mo_node.stage == ProvenanceStage.MODEL_OUTPUT
    assert mo_node.parent_hashes == [mi_node.content_hash]

    # 7. Decision Input (Final Recommendation)
    decision_input = DecisionInputRecord(
        recommendation_id=rec_id,
        asset_id=asset_id,
        action=StrategicAction.PURSUE,
        model_output_ids=[model_out.id],
        model_scores={"development_potential_score": 74.5},
        decision_policy_version="v1.0",
        thresholds_applied={"pursue_min_dps": 65.0},
    )
    di_node, merkle_root = engine.record_decision_input(decision_input)
    assert di_node.stage == ProvenanceStage.DECISION_INPUT
    assert len(merkle_root) == 64

    # TEST TRACEBACK BACK TO UNDERLYING SOURCES
    traceback = engine.trace_recommendation_back_to_sources(rec_id)
    assert traceback.unbroken_chain is True
    assert traceback.chain_length == 7
    assert traceback.action == StrategicAction.PURSUE
    assert len(traceback.underlying_sources) == 1
    assert traceback.underlying_sources[0].source_id == "PMID:38718468"
    assert traceback.underlying_sources[0].title == src.title

    # Verify stage steps in traceback
    assert traceback.terminal_decision.stage == ProvenanceStage.DECISION_INPUT
    assert traceback.model_output_step.stage == ProvenanceStage.MODEL_OUTPUT
    assert traceback.model_input_step.stage == ProvenanceStage.MODEL_INPUT
    assert len(traceback.feature_derivation_steps) == 1
    assert traceback.feature_derivation_steps[0].stage == ProvenanceStage.FEATURE_DERIVATION
    assert len(traceback.normalization_steps) == 1
    assert traceback.normalization_steps[0].stage == ProvenanceStage.NORMALIZATION
    assert len(traceback.extraction_steps) == 1
    assert traceback.extraction_steps[0].stage == ProvenanceStage.EXTRACTION


def test_provenance_graph_dag_and_merkle_root():
    """Verifies that the provenance graph is a validated DAG with cryptographic integrity."""
    engine = ProvenanceGraphEngine()
    asset_id = uuid4()
    rec_id = uuid4()

    src = EvidenceSource(
        source_type=SourceType.CLINICAL_TRIAL,
        source_id="NCT04886804",
        title="Beamion Lung-1",
        organization="Boehringer Ingelheim",
        publication_date=date(2023, 10, 15),
        retrieval_date=date(2023, 10, 20),
        url_reference="https://clinicaltrials.gov",
        study_type="interventional",
        temporal_validity=EvidenceTemporalScope(
            valid_from=date(2023, 10, 15),
            as_of_date=date(2023, 10, 15),
        ),
    )
    engine.record_source(src, asset_id)

    ext = EvidenceExtraction(
        source_id=src.id,
        source_location="Results Section",
        extracted_text="Grade 3 diarrhea rate was 3.9%",
        extracted_date=date(2023, 10, 15),
    )
    engine.record_extraction(ext, src, asset_id)

    norm = NormalizationRecord(
        extraction_id=ext.id,
        asset_id=asset_id,
        raw_value="3.9%",
        normalized_value=3.9,
        normalized_unit="%",
        parameter_name="diarrhea_rate",
        transformation_rule="pct_norm",
    )
    engine.record_normalization(norm, ext.id)

    feat = DerivedFeature(
        asset_id=asset_id,
        feature_name="safety_score",
        computed_value=85.0,
        calculation_formula="100 - (3.9 * 3.8)",
        source_observation_ids=[norm.id],
    )
    engine.record_feature_derivation(feat, [norm.id])

    mi = ModelInputRecord(
        model_name="SafetyModel",
        model_version="v0.1",
        asset_id=asset_id,
        feature_ids=[feat.id],
        feature_vector={"safety": 85.0},
    )
    engine.record_model_input(mi)

    mo = ModelOutput(
        asset_id=asset_id,
        model_name="SafetyModel",
        model_version="v0.1",
        output_metric="safety_score",
        output_value=85.0,
        derived_feature_ids=[feat.id],
    )
    engine.record_model_output(mo, mi.id)

    di = DecisionInputRecord(
        recommendation_id=rec_id,
        asset_id=asset_id,
        action=StrategicAction.PURSUE,
        model_output_ids=[mo.id],
        model_scores={"safety": 85.0},
    )
    _, merkle_root = engine.record_decision_input(di)

    graph = engine.get_provenance_graph(rec_id)
    assert graph.is_dag_valid is True
    assert graph.is_immutable_verified is True
    assert graph.merkle_root_hash == merkle_root
    assert len(graph.nodes) == 7
    assert len(graph.edges) == 6
    assert graph.stage_counts[ProvenanceStage.SOURCE] == 1
    assert graph.stage_counts[ProvenanceStage.DECISION_INPUT] == 1


def test_provenance_integrity_error_on_broken_chain():
    """Verifies that attempting to record a stage without parents raises ProvenanceIntegrityError."""
    engine = ProvenanceGraphEngine()
    asset_id = uuid4()
    orphan_uuid = uuid4()

    # Attempt to record normalization referencing non-existent extraction
    norm = NormalizationRecord(
        extraction_id=orphan_uuid,
        asset_id=asset_id,
        raw_value="invalid",
        normalized_value=0.0,
        normalized_unit="unit",
        parameter_name="param",
        transformation_rule="rule",
    )
    with pytest.raises(ProvenanceIntegrityError, match="references unknown extraction"):
        engine.record_normalization(norm, orphan_uuid)

    # Attempt to derive feature with empty parents
    feat = DerivedFeature(
        asset_id=asset_id,
        feature_name="empty_feature",
        computed_value=1.0,
        calculation_formula="formula",
        source_observation_ids=[],
    )
    with pytest.raises(ProvenanceIntegrityError, match="must have parents"):
        engine.record_feature_derivation(feat, [])


def test_provenance_api_endpoints(client: TestClient):
    """Verifies REST API endpoints for provenance graph and traceback."""
    # 1. Provenance Graph Endpoint
    resp_graph = client.get("/api/v1/decision/assets/zongertinib/provenance/graph")
    assert resp_graph.status_code == 200
    graph_data = resp_graph.json()
    assert graph_data["is_dag_valid"] is True
    assert graph_data["is_immutable_verified"] is True
    assert "merkle_root_hash" in graph_data
    assert len(graph_data["merkle_root_hash"]) == 64
    assert len(graph_data["nodes"]) >= 7
    assert len(graph_data["edges"]) >= 6

    # 2. Provenance Traceback Endpoint
    resp_trace = client.get("/api/v1/decision/assets/zongertinib/provenance/traceback")
    assert resp_trace.status_code == 200
    trace_data = resp_trace.json()
    assert trace_data["unbroken_chain"] is True
    assert trace_data["chain_length"] == 7
    assert trace_data["action"] == "PURSUE"
    assert len(trace_data["underlying_sources"]) >= 3
    assert any(s["source_id"] == "PMID:38718468" for s in trace_data["underlying_sources"])
    assert any(s["source_id"] == "NCT04886804" for s in trace_data["underlying_sources"])
    assert trace_data["terminal_decision"]["stage"] == "decision_input"
    assert trace_data["model_output_step"]["stage"] == "model_output"
    assert trace_data["model_input_step"]["stage"] == "model_input"
    assert len(trace_data["feature_derivation_steps"]) >= 4
    assert len(trace_data["normalization_steps"]) >= 4
    assert len(trace_data["extraction_steps"]) >= 4


def test_migration_031_exists():
    """Verifies that migration 031_immutable_provenance.sql exists with correct table definitions."""
    migration_path = Path("services/kg/migrations/031_immutable_provenance.sql")
    assert migration_path.exists(), "Migration 031_immutable_provenance.sql must exist"
    content = migration_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS provenance_normalizations" in content
    assert "CREATE TABLE IF NOT EXISTS provenance_model_inputs" in content
    assert "CREATE TABLE IF NOT EXISTS provenance_decision_inputs" in content
    assert "CREATE TABLE IF NOT EXISTS provenance_nodes" in content
    assert "CREATE TABLE IF NOT EXISTS provenance_edges" in content
    assert "CREATE TABLE IF NOT EXISTS provenance_merkle_audits" in content
