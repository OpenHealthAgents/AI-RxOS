from datetime import date
from pathlib import Path
from uuid import uuid4
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.opportunity_engine.evidence.models import (
    ConfidenceLevel,
    ProspectiveOrRetrospective,
    QualityGrade,
    RiskOfBias,
    SourceType,
)
from app.opportunity_engine.evidence.scoring import (
    DirectnessLevel,
    EvidenceQualityAppraisal,
    EvidenceQualityEngine,
    LowEvidenceConversionError,
    ModelRelevance,
    ReplicationStatus,
    StudyDesignType,
)
from app.opportunity_engine.evidence.service import EvidenceService


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_ten_dimension_evidence_quality_evaluation():
    """
    Verifies that all 10 dimensions are evaluated:
    1. peer review
    2. study design
    3. sample size
    4. model relevance
    5. human evidence
    6. prospective design
    7. replication
    8. source quality
    9. directness
    10. recency
    """
    appraisal = EvidenceQualityEngine.evaluate(
        peer_reviewed=True,
        study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
        sample_size=102,
        model_relevance=ModelRelevance.DIRECT_HUMAN_CLINICAL,
        is_human=True,
        prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
        replication_status=ReplicationStatus.INTERNALLY_REPLICATED,
        source_type=SourceType.CLINICAL_TRIAL,
        directness=DirectnessLevel.DIRECT,
        publication_date=date(2023, 10, 15),
        as_of_date=date(2024, 1, 1),
        risk_of_bias=RiskOfBias.LOW,
    )

    # Check that all 10 dimensions are evaluated
    expected_dims = {
        "peer_review",
        "study_design",
        "sample_size",
        "model_relevance",
        "human_evidence",
        "prospective_design",
        "replication",
        "source_quality",
        "directness",
        "recency",
    }
    assert set(appraisal.dimension_scores.keys()) == expected_dims
    assert set(appraisal.scoring_breakdown.keys()) == expected_dims

    # High quality clinical trial scores
    assert appraisal.overall_quality_score >= 80.0
    assert appraisal.quality_grade in (QualityGrade.GRADE_A_HIGH, QualityGrade.GRADE_B_MODERATE)
    assert appraisal.calibrated_confidence >= 0.80
    assert appraisal.confidence_level in (ConfidenceLevel.VERY_HIGH, ConfidenceLevel.HIGH)

    # Exposes quality, confidence, limitations
    assert appraisal.quality is not None
    assert appraisal.quality.quality_score == appraisal.overall_quality_score
    assert appraisal.confidence is not None
    assert appraisal.confidence.score == appraisal.calibrated_confidence
    assert isinstance(appraisal.limitations, list)

    # High confidence claims are allowed for high-quality evidence
    assert appraisal.is_high_confidence_claim_allowed is True
    assert appraisal.epistemic_warning is None


def test_epistemic_invariant_never_convert_low_evidence_into_high_confidence():
    """
    Verifies that low evidence is NEVER converted into high-confidence claims.
    Enforces LowEvidenceConversionError on assertion violations.
    """
    # Low quality: unreviewed in vitro cell line study, small sample, retrospective
    low_appraisal = EvidenceQualityEngine.evaluate(
        peer_reviewed=False,
        study_design=StudyDesignType.IN_VITRO_CELL_LINE,
        sample_size=6,
        model_relevance=ModelRelevance.IMMORTALIZED_CELL_LINE,
        is_human=False,
        prospective_or_retrospective=ProspectiveOrRetrospective.RETROSPECTIVE,
        replication_status=ReplicationStatus.SINGLE_STUDY_UNREPLICATED,
        source_type=SourceType.COMPANY_SOURCE,
        directness=DirectnessLevel.INDIRECT,
        publication_date=date(2023, 1, 1),
        as_of_date=date(2024, 1, 1),
        risk_of_bias=RiskOfBias.HIGH,
    )

    # Quality must be low / grade C or D
    assert low_appraisal.overall_quality_score < 50.0
    assert low_appraisal.quality_grade in (QualityGrade.GRADE_C_LOW, QualityGrade.GRADE_D_VERY_LOW)
    assert low_appraisal.calibrated_confidence < 0.50
    assert low_appraisal.confidence_level in (ConfidenceLevel.LOW, ConfidenceLevel.INSUFFICIENT)

    # Epistemic gate MUST block high-confidence claims
    assert low_appraisal.is_high_confidence_claim_allowed is False
    assert low_appraisal.epistemic_warning is not None
    assert "EPISTEMIC SAFETY INVARIANT" in low_appraisal.epistemic_warning

    # Limitations must be clearly exposed
    assert len(low_appraisal.limitations) >= 4
    assert any("peer review" in lim.lower() for lim in low_appraisal.limitations)
    assert any("preclinical" in lim.lower() or "translation" in lim.lower() for lim in low_appraisal.limitations)

    # Attempting to convert low evidence into high-confidence claim must raise LowEvidenceConversionError!
    with pytest.raises(LowEvidenceConversionError, match="Epistemic violation"):
        EvidenceQualityEngine.assert_claim_confidence_invariants(
            appraisal=low_appraisal,
            claimed_confidence=0.88,  # Attempting high confidence on Grade D evidence!
            claim_text="Molecule definitely cures metastatic disease in humans",
        )

    # But moderate/calibrated confidence assertion is allowed
    EvidenceQualityEngine.assert_claim_confidence_invariants(
        appraisal=low_appraisal,
        claimed_confidence=0.35,  # Low/exploratory confidence matches reality
        claim_text="Preliminary in vitro signal observed in single screen",
    )


def test_recency_and_replication_modifiers():
    """Verifies that recency and replication penalize or reward overall quality."""
    # Historical study (>10 years old) with contradicted status
    old_appraisal = EvidenceQualityEngine.evaluate(
        peer_reviewed=True,
        study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
        sample_size=40,
        model_relevance=ModelRelevance.DIRECT_HUMAN_CLINICAL,
        is_human=True,
        prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
        replication_status=ReplicationStatus.CONTRADICTED,
        source_type=SourceType.PUBLICATION,
        directness=DirectnessLevel.DIRECT,
        publication_date=date(2010, 5, 1),
        as_of_date=date(2024, 1, 1),
        risk_of_bias=RiskOfBias.LOW,
    )

    assert any("Older study" in lim for lim in old_appraisal.limitations)
    assert any("Contradictory findings" in lim for lim in old_appraisal.limitations)
    assert old_appraisal.dimension_scores["replication"].raw_score == 20.0


def test_evidence_service_quality_appraisal_exposure():
    """Verifies that EvidenceService calculates and exposes appraisals for all sources."""
    service = EvidenceService()
    asset_id = uuid4()

    src = service.register_evidence(
        asset_id=asset_id,
        source_type=SourceType.PUBLICATION,
        source_id="PMID:12345678",
        title="Double-Blind RCT in Advanced Oncology",
        authors=["Dr. Trialist"],
        organization="NEJM",
        publication_date=date(2023, 6, 1),
        retrieval_date=date(2023, 6, 2),
        url_reference="https://nejm.org/example",
        study_type="rct_double_blind",
        sample_size=320,
        peer_reviewed=True,
        prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
        species="Human",
        model="Clinical Cohort",
        risk_of_bias=RiskOfBias.LOW,
    )

    appraisal = service.get_source_appraisal(src.id)
    assert appraisal is not None
    assert appraisal.overall_quality_score >= 85.0
    assert appraisal.quality_grade == QualityGrade.GRADE_A_HIGH
    assert appraisal.quality.quality_score >= 85.0
    assert appraisal.confidence.confidence_level in (ConfidenceLevel.VERY_HIGH, ConfidenceLevel.HIGH)
    assert appraisal.is_high_confidence_claim_allowed is True


def test_evidence_quality_api_endpoint(client: TestClient):
    """Verifies GET /api/v1/decision/assets/{asset_id}/evidence/quality endpoint."""
    resp = client.get("/api/v1/decision/assets/zongertinib/evidence/quality")
    assert resp.status_code == 200
    data = resp.json()

    assert data["asset_id"] == "zongertinib"
    assert data["count"] >= 3
    assert len(data["appraisals"]) >= 3

    # Check first appraisal exposes quality, confidence, and limitations
    appr = data["appraisals"][0]
    assert "source_id" in appr
    assert "overall_quality_score" in appr
    assert "quality_grade" in appr
    assert "calibrated_confidence" in appr
    assert "confidence_level" in appr
    assert "dimension_scores" in appr
    assert len(appr["dimension_scores"]) == 10
    assert "quality" in appr
    assert "confidence" in appr
    assert "limitations" in appr
    assert "is_high_confidence_claim_allowed" in appr


def test_migration_032_exists():
    """Verifies that migration 032_evidence_quality_scoring.sql exists."""
    migration_path = Path("services/kg/migrations/032_evidence_quality_scoring.sql")
    assert migration_path.exists(), "Migration 032_evidence_quality_scoring.sql must exist"
    content = migration_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS evidence_quality_appraisals" in content
    assert "CREATE TABLE IF NOT EXISTS claim_epistemic_audits" in content
    assert "peer_review_score" in content
    assert "limitations" in content
