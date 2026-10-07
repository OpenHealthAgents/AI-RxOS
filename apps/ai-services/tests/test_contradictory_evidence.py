import pytest
from datetime import date
from uuid import UUID, uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.domain.canonical_model import EvidencePolarity
from app.opportunity_engine.evidence.contradiction import (
    ContradictionEngine,
    ContradictionRecord,
    ContradictionReport,
    ContradictoryClaim,
    DisagreementCategory,
    DisagreementResolutionStatus,
    SilentSelectionViolationError,
)
from app.opportunity_engine.evidence.models import (
    ConfidenceLevel,
    EvidenceConfidence,
    EvidenceQuality,
    EvidenceSource,
    EvidenceTemporalScope,
    ProspectiveOrRetrospective,
    QualityGrade,
    RiskOfBias,
    SourceType,
)
from app.opportunity_engine.evidence.scoring import StudyDesignType
from app.opportunity_engine.evidence.service import EvidenceService


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def dummy_source_a() -> EvidenceSource:
    return EvidenceSource(
        source_type=SourceType.PUBLICATION,
        source_id="PUB-TEST-001",
        title="Preclinical In Vitro Selectivity Profile",
        organization="Dana-Farber Cancer Institute",
        publication_date=date(2023, 1, 15),
        retrieval_date=date(2023, 1, 20),
        url_reference="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        study_type="biochemical_kinase_assay",
        sample_size=30,
        peer_reviewed=True,
        prospective_or_retrospective=ProspectiveOrRetrospective.NOT_APPLICABLE,
        temporal_validity=EvidenceTemporalScope(
            valid_from=date(2023, 1, 15),
            as_of_date=date.today(),
            is_current=True,
        ),
    )


@pytest.fixture
def dummy_source_b() -> EvidenceSource:
    return EvidenceSource(
        source_type=SourceType.CLINICAL_TRIAL,
        source_id="NCT-TEST-002",
        title="Phase 1b Single-Arm Clinical Trial",
        organization="Memorial Sloan Kettering",
        publication_date=date(2024, 3, 10),
        retrieval_date=date(2024, 3, 15),
        url_reference="https://clinicaltrials.gov/study/NCT98765432",
        study_type="phase_1_2_single_arm",
        sample_size=45,
        peer_reviewed=True,
        prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
        temporal_validity=EvidenceTemporalScope(
            valid_from=date(2024, 3, 10),
            as_of_date=date.today(),
            is_current=True,
        ),
    )


def test_polarities_supported():
    """Verify all 4 required evidence polarity states are valid and recognized."""
    polarities = [
        EvidencePolarity.SUPPORTING,
        EvidencePolarity.CONTRADICTORY,
        EvidencePolarity.NEUTRAL,
        EvidencePolarity.UNKNOWN,
    ]
    for pol in polarities:
        assert pol.value in ["SUPPORTING", "CONTRADICTORY", "NEUTRAL", "UNKNOWN"]


def test_silent_selection_violation_raised():
    """Invariant: An automated pipeline must not silently select or drop conflicting credible sources."""
    engine = ContradictionEngine()
    source = EvidenceSource(
        source_type=SourceType.PUBLICATION,
        source_id="SRC-1",
        title="Title",
        organization="Org",
        publication_date=date(2023, 1, 1),
        retrieval_date=date(2023, 1, 2),
        url_reference="https://example.com",
        study_type="rct",
        temporal_validity=EvidenceTemporalScope(
            valid_from=date(2023, 1, 1),
            as_of_date=date.today(),
        ),
    )
    claim_a = ContradictoryClaim(
        claim_text="Drug induces 70% ORR in HER2 Exon 20 insertion patients.",
        polarity=EvidencePolarity.SUPPORTING,
        source=source,
        date=date(2023, 1, 1),
        study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
        quality=EvidenceQuality(quality_score=85.0),
        confidence=EvidenceConfidence(score=0.90),
    )
    claim_b = ContradictoryClaim(
        claim_text="Real-world registry shows only 22% ORR with rapid disease progression.",
        polarity=EvidencePolarity.CONTRADICTORY,
        source=source,
        date=date(2024, 1, 1),
        study_design=StudyDesignType.RETROSPECTIVE_OBSERVATIONAL,
        quality=EvidenceQuality(quality_score=80.0),
        confidence=EvidenceConfidence(score=0.75),
    )

    with pytest.raises(SilentSelectionViolationError) as exc_info:
        engine.adjudicate_without_suppression(claim_a, claim_b, allow_silent_drop=True)

    assert "Silent selection is strictly prohibited" in str(exc_info.value)


def test_contradiction_record_delta_calculation(dummy_source_a, dummy_source_b):
    """Contradiction record correctly calculates quality and confidence deltas."""
    asset_id = uuid4()
    claim_a = ContradictoryClaim(
        claim_text="Kinase assay demonstrates 80-fold selectivity over WT-EGFR.",
        polarity=EvidencePolarity.SUPPORTING,
        source=dummy_source_a,
        date=date(2023, 1, 15),
        study_design=StudyDesignType.BIOCHEMICAL_KINASE_ASSAY,
        quality=EvidenceQuality(quality_score=90.0),
        confidence=EvidenceConfidence(score=0.95),
        numeric_measurement="80x",
    )
    claim_b = ContradictoryClaim(
        claim_text="Clinical trial reports 12% Grade 3 EGFR-associated rash at therapeutic dose.",
        polarity=EvidencePolarity.CONTRADICTORY,
        source=dummy_source_b,
        date=date(2024, 3, 10),
        study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
        quality=EvidenceQuality(quality_score=82.5),
        confidence=EvidenceConfidence(score=0.85),
        numeric_measurement="12% Grade 3",
    )

    record = ContradictionRecord(
        asset_id=asset_id,
        topic="EGFR Wild-Type Sparing Margin",
        parameter_name="wt_egfr_rash_rate",
        category=DisagreementCategory.SAFETY_TOXICITY_CONFLICT,
        claim_a=claim_a,
        claim_b=claim_b,
        possible_explanation="Assay disparity: High selectivity in cell-free assays does not eliminate cutaneous EGFR binding at Cmax peak.",
        resolution_recommendation="Monitor skin toxicity during Phase 2 dose expansion.",
    )

    assert record.quality_delta == 7.5  # abs(90.0 - 82.5)
    assert record.confidence_delta == 0.10  # abs(0.95 - 0.85)
    assert record.silent_selection_prevented is True
    assert "EPISTEMIC DISAGREEMENT DETECTED" in record.epistemic_warning


def test_explanation_synthesis(dummy_source_a, dummy_source_b):
    """Engine synthesizes reasoned explanations combining study design and sample size differences."""
    engine = ContradictionEngine()
    claim_a = ContradictoryClaim(
        claim_text="Preclinical xenograft model shows 90% intracranial shrinkage.",
        polarity=EvidencePolarity.SUPPORTING,
        source=dummy_source_a,
        date=date(2023, 1, 15),
        study_design=StudyDesignType.IN_VIVO_ANIMAL_DISEASE_MODEL,
        quality=EvidenceQuality(quality_score=75.0),
        confidence=EvidenceConfidence(score=0.80),
        sample_size=10,
    )
    claim_b = ContradictoryClaim(
        claim_text="Phase 1b cohort shows 28% CNS response in human patients with prior radiotherapy.",
        polarity=EvidencePolarity.CONTRADICTORY,
        source=dummy_source_b,
        date=date(2024, 3, 10),
        study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
        quality=EvidenceQuality(quality_score=88.0),
        confidence=EvidenceConfidence(score=0.85),
        sample_size=60,
    )

    explanation = engine.synthesize_explanation(
        DisagreementCategory.CNS_PENETRATION_DISCREPANCY,
        claim_a,
        claim_b,
    )

    assert "Design disparity" in explanation
    assert "Sample size power divergence" in explanation
    assert "Temporal evolution" in explanation
    assert "Mechanistic hypothesis" in explanation
    assert "P-gp/BCRP efflux" in explanation


def test_evidence_service_bootstrap_contradictions():
    """EvidenceService bootstraps realistic clinical contradictions for Zongertinib."""
    service = EvidenceService()
    zong_id = UUID("33333333-3333-3333-3333-333333333333")

    contradictions = service.get_asset_contradictions(zong_id)
    assert len(contradictions) >= 2

    # Check CNS Discrepancy Record
    cns_records = [c for c in contradictions if c.category == DisagreementCategory.CNS_PENETRATION_DISCREPANCY]
    assert len(cns_records) == 1
    cns_rec = cns_records[0]
    assert cns_rec.claim_a.polarity == EvidencePolarity.SUPPORTING
    assert cns_rec.claim_b.polarity == EvidencePolarity.CONTRADICTORY
    assert cns_rec.claim_a.study_design == StudyDesignType.IN_VIVO_ANIMAL_DISEASE_MODEL
    assert cns_rec.claim_b.study_design == StudyDesignType.PHASE_1_2_SINGLE_ARM
    assert cns_rec.silent_selection_prevented is True

    # Check Safety Discrepancy Record
    safety_records = [c for c in contradictions if c.category == DisagreementCategory.SAFETY_TOXICITY_CONFLICT]
    assert len(safety_records) == 1
    safety_rec = safety_records[0]
    assert safety_rec.claim_a.study_design == StudyDesignType.BIOCHEMICAL_KINASE_ASSAY
    assert safety_rec.claim_b.study_design == StudyDesignType.PHASE_1_2_SINGLE_ARM
    assert safety_rec.quality_delta == 4.0

    # Check Contradiction Report
    report = service.get_asset_contradiction_report(zong_id, asset_name="Zongertinib")
    assert report.total_contradictions >= 2
    assert report.asset_name == "Zongertinib"
    assert "Zero-Silent-Selection Guarantee" in report.epistemic_disclaimer


def test_api_contradiction_endpoints(test_client):
    """API endpoints serve contradictory evidence pairs and summary reports."""
    # 1. Contradictions list endpoint
    resp = test_client.get("/api/v1/decision/assets/zongertinib/evidence/contradictions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == "zongertinib"
    assert data["silent_selection_prevented"] is True
    assert data["total_contradictions"] >= 2

    first_item = data["contradictions"][0]
    assert "claim_a" in first_item
    assert "claim_b" in first_item
    assert "possible_explanation" in first_item
    assert "epistemic_warning" in first_item
    assert "quality_delta" in first_item
    assert "confidence_delta" in first_item

    # Verify Claim A & Claim B contain source and study design
    assert first_item["claim_a"]["polarity"] in ["SUPPORTING", "CONTRADICTORY", "NEUTRAL", "UNKNOWN"]
    assert first_item["claim_b"]["polarity"] in ["SUPPORTING", "CONTRADICTORY", "NEUTRAL", "UNKNOWN"]
    assert "study_design" in first_item["claim_a"]
    assert "quality" in first_item["claim_a"]
    assert "confidence" in first_item["claim_a"]

    # 2. Contradiction report endpoint
    report_resp = test_client.get("/api/v1/decision/assets/zongertinib/evidence/contradiction-report")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["asset_name"] == "Zongertinib"
    assert report_data["total_contradictions"] >= 2
    assert "epistemic_disclaimer" in report_data
