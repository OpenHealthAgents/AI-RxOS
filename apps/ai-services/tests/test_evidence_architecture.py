from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.opportunity_engine.domain.canonical_model import (
    EvidencePolarity,
    ScientificEvidenceState,
    StrategicAction,
)
from app.opportunity_engine.evidence import (
    DerivedFeature,
    Evidence,
    EvidenceCitation,
    EvidenceClaim,
    EvidenceConfidence,
    EvidenceExtraction,
    EvidenceLineageEngine,
    EvidenceLineageGraph,
    EvidenceObservation,
    EvidenceQuality,
    EvidenceRelationship,
    EvidenceService,
    EvidenceSource,
    EvidenceTemporalScope,
    ExtractionMethod,
    LineageStep,
    ModelOutput,
    OrphanedScoreError,
    ProspectiveOrRetrospective,
    QualityGrade,
    RiskOfBias,
    SourceType,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_evidence_sources_all_eight_types() -> None:
    """
    Verifies that all 8 required source types are supported with all 18 attributes:
    source_type, source_id, title, authors, organization, publication_date,
    retrieval_date, url/reference, study_type, phase, species, model, sample_size,
    peer_reviewed, prospective_or_retrospective, quality_score, confidence, temporal_validity.
    """
    service = EvidenceService()
    test_asset_id = uuid4()
    sources_to_test = [
        (SourceType.PUBLICATION, "PMID:38718468", "Nature Cancer Paper", "interventional_trial"),
        (SourceType.CLINICAL_TRIAL, "NCT04886804", "Beamion Lung-1", "interventional_clinical_trial"),
        (SourceType.REGULATORY_SOURCE, "FDA-NDA-213051", "FDA Label Approval", "regulatory_review"),
        (SourceType.PATENT, "US-11453678-B2", "Substituted Pyrimidines", "patent_grant"),
        (SourceType.COMPANY_SOURCE, "BI-PRESS-2023-01", "Boehringer Ingelheim Pipeline Update", "corporate_disclosure"),
        (SourceType.CONFERENCE_ABSTRACT, "AACR-2023-4521", "AACR Intracranial Study", "conference_proceedings"),
        (SourceType.SCIENTIFIC_DATABASE, "CHEMBL429810", "ChEMBL Kinase Bioassay", "cheminformatics_database"),
        (SourceType.INSTITUTIONAL_SOURCE, "DFCI-PROTO-2022", "Dana-Farber Translational Consortium", "institutional_protocol"),
    ]

    for stype, sid, title, study_type in sources_to_test:
        src = service.register_evidence(
            asset_id=test_asset_id,
            source_type=stype,
            source_id=sid,
            title=title,
            authors=["Dr. Scientist", "Prof. Clinician"],
            organization="Academic & Pharma Consortium",
            publication_date=date(2023, 6, 1),
            retrieval_date=date(2023, 6, 15),
            url_reference="https://dx.doi.org/10.1000/182",
            study_type=study_type,
            phase="Phase 1",
            species="Human",
            model="Clinical Cohort",
            sample_size=85,
            peer_reviewed=True,
            prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
            risk_of_bias=RiskOfBias.LOW,
            confidence_score=0.92,
        )

        assert src.source_type == stype
        assert src.source_id == sid
        assert src.title == title
        assert len(src.authors) == 2
        assert src.organization == "Academic & Pharma Consortium"
        assert src.publication_date == date(2023, 6, 1)
        assert src.retrieval_date == date(2023, 6, 15)
        assert src.url_reference.startswith("https://")
        assert src.study_type == study_type
        assert src.phase == "Phase 1"
        assert src.species == "Human"
        assert src.model == "Clinical Cohort"
        assert src.sample_size == 85
        assert src.peer_reviewed is True
        assert src.prospective_or_retrospective == ProspectiveOrRetrospective.PROSPECTIVE
        assert src.quality_score >= 80.0
        assert src.confidence == 0.92
        assert src.temporal_validity.valid_from == date(2023, 6, 1)
        assert src.temporal_validity.is_current is True


def test_extracted_observations_retains_required_attributes() -> None:
    """
    Each extracted observation must retain:
    source, source location, extracted text/value, normalized value, unit,
    entity, date, extraction method, confidence.
    """
    service = EvidenceService()
    test_asset_id = uuid4()
    src = service.register_evidence(
        asset_id=test_asset_id,
        source_type=SourceType.PUBLICATION,
        source_id="PMID:38718468",
        title="Test Observation Paper",
        authors=["Author A"],
        organization="Nature",
        publication_date=date(2024, 1, 1),
        retrieval_date=date(2024, 1, 10),
        url_reference="https://pubmed.ncbi.nlm.nih.gov/38718468/",
        study_type="in_vitro",
    )

    obs = service.add_extraction_and_observation(
        source=src,
        asset_id=test_asset_id,
        source_location="Table 2, row 4",
        extracted_text="Mean IC50 was 2.4 nM against HER2 exon 20 insertion",
        entity="HER2 exon 20 ins",
        parameter_name="ic50_nm",
        normalized_value=2.4,
        unit="nM",
        observation_date=date(2024, 1, 1),
        extraction_method=ExtractionMethod.LLM_STRUCTURED_EXTRACTION,
        confidence=0.95,
        polarity=EvidencePolarity.SUPPORTING,
        observation_state=ScientificEvidenceState.VERIFIED_FACT,
    )

    assert obs.source_ref == "PMID:38718468"
    assert obs.source_location == "Table 2, row 4"
    assert "Mean IC50 was 2.4 nM" in obs.extracted_text_or_value
    assert obs.normalized_value == 2.4
    assert obs.unit == "nM"
    assert obs.entity == "HER2 exon 20 ins"
    assert obs.observation_date == date(2024, 1, 1)
    assert obs.extraction_method == ExtractionMethod.LLM_STRUCTURED_EXTRACTION
    assert obs.confidence == 0.95
    assert obs.polarity == EvidencePolarity.SUPPORTING
    assert obs.observation_state == ScientificEvidenceState.VERIFIED_FACT


def test_evidence_lineage_pipeline_end_to_end() -> None:
    """
    Tests complete evidence lineage chain:
    Source -> extraction -> normalized observation -> derived feature -> model output -> recommendation.
    Verifies graph traversal and cryptographic lineage hash.
    """
    engine = EvidenceLineageEngine()
    asset_id = uuid4()
    rec_id = uuid4()

    # 1. Source
    src = EvidenceSource(
        source_type=SourceType.PUBLICATION,
        source_id="PMID:999999",
        title="Selectivity and Efficacy Study",
        organization="Oncology Lab",
        publication_date=date(2023, 5, 1),
        retrieval_date=date(2023, 5, 2),
        url_reference="https://doi.org/10.1038/example",
        study_type="in_vivo",
        temporal_validity=EvidenceTemporalScope(
            valid_from=date(2023, 5, 1),
            as_of_date=date(2023, 5, 1),
        ),
    )
    engine.register_source(src)

    # 2. Extraction
    extraction = EvidenceExtraction(
        source_id=src.id,
        source_location="Page 4, Table 1",
        extracted_text="Wild-type EGFR sparing ratio was 65.4x",
        extracted_date=date(2023, 5, 1),
    )
    engine.add_extraction(extraction)

    # 3. Normalized Observation
    obs = EvidenceObservation(
        extraction_id=extraction.id,
        source_id=src.id,
        source_ref=src.source_id,
        asset_id=asset_id,
        entity="EGFR WT",
        parameter_name="wt_sparing_ratio",
        extracted_text_or_value=extraction.extracted_text,
        normalized_value=65.4,
        unit="fold_ratio",
        observation_date=date(2023, 5, 1),
        source_location="Page 4, Table 1",
        confidence=0.95,
    )
    engine.add_observation(obs)

    # 4. Derived Feature
    feature = engine.derive_feature(
        asset_id=asset_id,
        feature_name="target_selectivity_metric",
        computed_value=93.5,
        calculation_formula="min(100, 50 + log10(ratio) * 24)",
        source_observation_ids=[obs.id],
    )

    # 5. Model Output
    model_output = engine.record_model_output(
        asset_id=asset_id,
        model_name="UtilityScorer",
        output_metric="development_potential_score",
        output_value=72.0,
        derived_feature_ids=[feature.id],
    )

    # 6. Recommendation
    rec_lineage = engine.link_recommendation(
        recommendation_id=rec_id,
        asset_id=asset_id,
        action=StrategicAction.PURSUE,
        model_output_ids=[model_output.id],
    )

    assert rec_lineage.lineage_hash is not None
    assert len(rec_lineage.lineage_hash) == 64  # SHA-256

    # Verify complete unbroken graph
    is_complete, orphans = engine.verify_lineage_integrity(rec_id)
    assert is_complete is True
    assert len(orphans) == 0

    graph = engine.get_lineage_graph(rec_id, asset_id)
    assert len(graph.sources) == 1
    assert len(graph.extractions) == 1
    assert len(graph.observations) == 1
    assert len(graph.derived_features) == 1
    assert len(graph.model_outputs) == 1
    assert graph.is_lineage_complete is True


def test_orphaned_scientific_scores_are_strictly_rejected() -> None:
    """
    Guarantees that no orphaned scientific score or decision can exist without lineage.
    """
    engine = EvidenceLineageEngine()
    asset_id = uuid4()
    rec_id = uuid4()

    # Attempt to derive feature without observations -> Must raise OrphanedScoreError
    with pytest.raises(OrphanedScoreError, match="must be backed by at least one evidence observation"):
        engine.derive_feature(
            asset_id=asset_id,
            feature_name="unbacked_selectivity",
            computed_value=95.0,
            calculation_formula="arbitrary_guess",
            source_observation_ids=[],  # Empty!
        )

    # Attempt to produce model output without features -> Must raise OrphanedScoreError
    with pytest.raises(OrphanedScoreError, match="must be backed by derived features"):
        engine.record_model_output(
            asset_id=asset_id,
            model_name="FakePredictor",
            output_metric="dps",
            output_value=80.0,
            derived_feature_ids=[],  # Empty!
        )

    # Attempt to link recommendation without model outputs -> Must raise OrphanedScoreError
    with pytest.raises(OrphanedScoreError, match="must be backed by at least one model output"):
        engine.link_recommendation(
            recommendation_id=rec_id,
            asset_id=asset_id,
            action=StrategicAction.PURSUE,
            model_output_ids=[],  # Empty!
        )


def test_temporal_cutoff_prevents_information_leakage() -> None:
    """
    Verifies that evidence published after a temporal cutoff date is strictly
    omitted from asset evaluation.
    """
    service = EvidenceService()
    asset_id = UUID("33333333-3333-3333-3333-333333333333")

    # In 2022, only pre-2023 evidence should be visible
    evidence_2022 = service.get_asset_evidence(asset_id, cutoff_date=date(2022, 12, 31))
    for ev in evidence_2022:
        assert ev.publication_date <= date(2022, 12, 31)

    # None of the 2023 or 2024 papers or trials should be in evidence_2022
    assert not any(ev.source_id == "PMID:38718468" for ev in evidence_2022)
    assert not any(ev.source_id == "NCT04886804" for ev in evidence_2022)

    # In 2024, all evidence including Nature Cancer 2024 is visible
    evidence_2024 = service.get_asset_evidence(asset_id, cutoff_date=date(2024, 12, 31))
    assert any(ev.source_id == "PMID:38718468" for ev in evidence_2024)
    assert len(evidence_2024) > len(evidence_2022)


def test_evidence_api_endpoints(client: TestClient) -> None:
    """
    Tests evidence REST API endpoints for inspection, lineage graphs, and integrity audits.
    """
    # 1. Evidence List Endpoint
    resp = client.get("/api/v1/decision/assets/zongertinib/evidence")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "zongertinib"
    assert data["count"] >= 3
    assert len(data["evidence"]) >= 3

    # Check first evidence item has full provenance
    first_ev = data["evidence"][0]
    assert "source_type" in first_ev
    assert "quality_score" in first_ev
    assert "observations" in first_ev
    assert len(first_ev["observations"]) > 0

    # 2. Lineage Graph Endpoint
    resp_lineage = client.get("/api/v1/decision/assets/zongertinib/lineage")
    assert resp_lineage.status_code == 200
    lineage_data = resp_lineage.json()
    assert lineage_data["is_lineage_complete"] is True
    assert len(lineage_data["sources"]) > 0
    assert len(lineage_data["observations"]) > 0
    assert len(lineage_data["derived_features"]) > 0
    assert len(lineage_data["model_outputs"]) > 0
    assert len(lineage_data["relationships"]) > 0

    # 3. Lineage Verification Endpoint
    resp_verify = client.get("/api/v1/decision/assets/zongertinib/lineage/verify")
    assert resp_verify.status_code == 200
    verify_data = resp_verify.json()
    assert verify_data["is_lineage_complete"] is True
    assert verify_data["orphaned_scores_count"] == 0
    assert verify_data["audit_pass"] is True


def test_database_migration_014_exists() -> None:
    """Verifies that 014_evidence_architecture.sql migration file exists with correct schema."""
    migration_path = Path("services/kg/migrations/014_evidence_architecture.sql")
    assert migration_path.exists(), "Migration 014_evidence_architecture.sql does not exist"
    content = migration_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS evidence_sources" in content
    assert "CREATE TABLE IF NOT EXISTS evidence_extractions" in content
    assert "CREATE TABLE IF NOT EXISTS evidence_observations_rich" in content
    assert "CREATE TABLE IF NOT EXISTS evidence_claims" in content
    assert "CREATE TABLE IF NOT EXISTS derived_features" in content
    assert "CREATE TABLE IF NOT EXISTS model_outputs" in content
    assert "CREATE TABLE IF NOT EXISTS recommendation_lineages" in content
    assert "CREATE TABLE IF NOT EXISTS evidence_relationships" in content
    assert "idx_evidence_sources_type_id" in content
    assert "idx_evidence_sources_temporal" in content
