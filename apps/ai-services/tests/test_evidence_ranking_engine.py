"""
Tests for Evidence Ranking across all 9 canonical dimensions:
1. source quality
2. directness
3. recency
4. human relevance
5. study design
6. sample size
7. peer review
8. confidence
9. temporal validity

Verifies:
- Evidence ranked with comprehensive ranking rationale
- Multi-dimensional breakdown of all 9 factors
- Penalization and tier assignment for temporal invalidity / leakage
- Comparison across study designs (Pivotal Phase 3 vs Preclinical In Vitro)
- REST API endpoints (GET /evidence/ranked and POST /evidence/rank)
"""

from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.evidence import (
    DirectnessLevel,
    EvidenceRankingEngine,
    EvidenceRankingRecord,
    EvidenceRankingResult,
    EvidenceRankingTier,
    EvidenceService,
    ModelRelevance,
    SourceType,
    StudyDesignType,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def evidence_service() -> EvidenceService:
    return EvidenceService()


def test_ranking_nine_dimensions_evaluated() -> None:
    """
    Verifies that EvidenceRankingEngine evaluates all 9 dimensions:
    1. source quality
    2. directness
    3. recency
    4. human relevance
    5. study design
    6. sample size
    7. peer review
    8. confidence
    9. temporal validity
    """
    record = EvidenceRankingEngine.score_single_evidence(
        evidence_id="ev-001",
        title="Pivotal Phase 3 Randomized Controlled Trial in HER2+ Breast Cancer",
        source_citation="Murthy et al. NEJM 2020",
        source_type=SourceType.CLINICAL_TRIAL,
        directness=DirectnessLevel.DIRECT,
        is_human=True,
        model_relevance=ModelRelevance.DIRECT_HUMAN_CLINICAL,
        study_design=StudyDesignType.RCT_DOUBLE_BLIND,
        sample_size=612,
        peer_reviewed=True,
        confidence_score=0.98,
        publication_date=date(2020, 2, 13),
        as_of_date=date(2021, 1, 1),
    )

    # 1. Check all 8 scored dimensions are present in dimension_scores
    expected_dims = {
        "source_quality",
        "directness",
        "recency",
        "human_relevance",
        "study_design",
        "sample_size",
        "peer_review",
        "confidence",
    }
    assert set(record.dimension_scores.keys()) == expected_dims

    # 2. Check 9th dimension: temporal validity
    assert record.is_temporally_valid is True

    # 3. Check composite score and Tier 1 pinnacle
    assert record.composite_rank_score >= 85.0
    assert record.ranking_tier == EvidenceRankingTier.TIER_1_PINNACLE

    # 4. Check ranking rationale is detailed and explicit
    assert len(record.ranking_rationale) > 50
    assert "TIER_1_PINNACLE" in record.ranking_rationale
    assert "Source:" in record.ranking_rationale
    assert "Directness & Human Relevance:" in record.ranking_rationale
    assert "Study Rigor:" in record.ranking_rationale

    # 5. Check strengths and limitations
    assert any("Direct human clinical patients" in s for s in record.key_strengths)
    assert any("Large statistical sample cohort" in s for s in record.key_strengths)


def test_ranking_hierarchy_pivotal_human_vs_preclinical_in_vitro() -> None:
    """
    Verifies that high-rigor human trials rank strictly higher than in vitro preclinical assays.
    """
    pivotal_trial = {
        "id": str(uuid4()),
        "title": "Phase 3 Double-Blind RCT in Human Patients",
        "source_type": SourceType.CLINICAL_TRIAL,
        "directness": DirectnessLevel.DIRECT,
        "is_human": True,
        "model_relevance": ModelRelevance.DIRECT_HUMAN_CLINICAL,
        "study_design": StudyDesignType.RCT_DOUBLE_BLIND,
        "sample_size": 450,
        "peer_reviewed": True,
        "confidence": 0.96,
        "publication_date": date(2023, 5, 10),
    }

    in_vitro_assay = {
        "id": str(uuid4()),
        "title": "In Vitro Cell Line Proliferation Assay",
        "source_type": SourceType.PUBLICATION,
        "directness": DirectnessLevel.PROXIMATE,
        "is_human": False,
        "model_relevance": ModelRelevance.IMMORTALIZED_CELL_LINE,
        "study_design": StudyDesignType.IN_VITRO_CELL_LINE,
        "sample_size": 3,
        "peer_reviewed": True,
        "confidence": 0.85,
        "publication_date": date(2023, 5, 10),
    }

    res = EvidenceRankingEngine.rank_evidence_list([in_vitro_assay, pivotal_trial])

    assert len(res.ranked_evidence) == 2
    # Pivotal trial must be #1
    assert res.ranked_evidence[0].ranking == 1
    assert res.ranked_evidence[0].title == "Phase 3 Double-Blind RCT in Human Patients"
    assert res.ranked_evidence[0].composite_rank_score > res.ranked_evidence[1].composite_rank_score
    assert res.ranked_evidence[0].ranking_tier in (EvidenceRankingTier.TIER_1_PINNACLE, EvidenceRankingTier.TIER_2_HIGH)
    assert res.ranked_evidence[1].ranking_tier in (EvidenceRankingTier.TIER_3_MODERATE, EvidenceRankingTier.TIER_4_LOW)


def test_recency_penalty_on_older_evidence() -> None:
    """
    Verifies that newer evidence scores higher on recency than decade-old evidence.
    """
    recent_item = EvidenceRankingEngine.score_single_evidence(
        evidence_id="rec-001",
        title="Recent Trial 2024",
        source_citation="Citation 2024",
        source_type=SourceType.CLINICAL_TRIAL,
        directness=DirectnessLevel.DIRECT,
        is_human=True,
        model_relevance=ModelRelevance.DIRECT_HUMAN_CLINICAL,
        study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
        sample_size=80,
        peer_reviewed=True,
        confidence_score=0.90,
        publication_date=date(2024, 1, 15),
        as_of_date=date(2024, 6, 1),
    )

    old_item = EvidenceRankingEngine.score_single_evidence(
        evidence_id="old-001",
        title="Old Trial 2011",
        source_citation="Citation 2011",
        source_type=SourceType.CLINICAL_TRIAL,
        directness=DirectnessLevel.DIRECT,
        is_human=True,
        model_relevance=ModelRelevance.DIRECT_HUMAN_CLINICAL,
        study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
        sample_size=80,
        peer_reviewed=True,
        confidence_score=0.90,
        publication_date=date(2011, 1, 15),
        as_of_date=date(2024, 6, 1),
    )

    assert recent_item.dimension_scores["recency"].raw_score == 100.0
    assert old_item.dimension_scores["recency"].raw_score < 50.0
    assert recent_item.composite_rank_score > old_item.composite_rank_score


def test_temporal_validity_gatekeeper_penalizes_future_leakage() -> None:
    """
    CRITICAL INVARIANT TEST:
    Evidence published after prediction cutoff must be flagged as temporally invalid,
    severely penalized, and categorized into TIER_5_INSUFFICIENT.
    """
    leaked_evidence = EvidenceRankingEngine.score_single_evidence(
        evidence_id="leak-001",
        title="Post-Cutoff Breakthrough Clinical Result",
        source_citation="Future Journal 2024",
        source_type=SourceType.CLINICAL_TRIAL,
        directness=DirectnessLevel.DIRECT,
        is_human=True,
        model_relevance=ModelRelevance.DIRECT_HUMAN_CLINICAL,
        study_design=StudyDesignType.RCT_DOUBLE_BLIND,
        sample_size=500,
        peer_reviewed=True,
        confidence_score=0.99,
        publication_date=date(2024, 5, 1),
        prediction_cutoff=date(2023, 1, 1),  # Published after cutoff!
    )

    assert leaked_evidence.is_temporally_valid is False
    assert leaked_evidence.ranking_tier == EvidenceRankingTier.TIER_5_INSUFFICIENT
    assert leaked_evidence.composite_rank_score < 25.0
    assert "Future information leakage" in leaked_evidence.ranking_rationale


def test_service_rank_asset_evidence(evidence_service: EvidenceService) -> None:
    """
    Tests ranking all registered evidence for Zongertinib.
    """
    zong_id = UUID("33333333-3333-3333-3333-333333333333")
    res = evidence_service.rank_asset_evidence(asset_id=zong_id)

    assert res.total_candidates >= 5
    assert len(res.ranked_evidence) >= 5

    # Verifies ranking is strictly 1-based and ordered descending
    scores = [r.composite_rank_score for r in res.ranked_evidence]
    assert scores == sorted(scores, reverse=True)
    assert [r.ranking for r in res.ranked_evidence] == list(range(1, len(scores) + 1))

    # Top item must have rationale
    top = res.ranked_evidence[0]
    assert len(top.ranking_rationale) > 20
    assert top.ranking_tier in (EvidenceRankingTier.TIER_1_PINNACLE, EvidenceRankingTier.TIER_2_HIGH)


def test_api_ranked_asset_evidence(client: TestClient) -> None:
    """Tests GET /api/v1/decision/evidence/ranked/{asset_id}."""
    resp = client.get("/api/v1/decision/evidence/ranked/33333333-3333-3333-3333-333333333333")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_candidates"] >= 5
    assert len(data["ranked_evidence"]) >= 5
    top = data["ranked_evidence"][0]
    assert "ranking_rationale" in top
    assert "dimension_scores" in top
    assert "source_quality" in top["dimension_scores"]
    assert "directness" in top["dimension_scores"]
    assert "recency" in top["dimension_scores"]
    assert "human_relevance" in top["dimension_scores"]
    assert "study_design" in top["dimension_scores"]
    assert "sample_size" in top["dimension_scores"]
    assert "peer_review" in top["dimension_scores"]
    assert "confidence" in top["dimension_scores"]


def test_api_rank_custom_evidence_list(client: TestClient) -> None:
    """Tests POST /api/v1/decision/evidence/rank."""
    payload = {
        "query_context": "Evaluation of HER2 evidence",
        "as_of_date": "2024-01-01",
        "evidence_items": [
            {
                "id": str(uuid4()),
                "title": "Study A",
                "source_type": "clinical_trial",
                "study_design": "phase_1_2_single_arm",
                "sample_size": 100,
                "peer_reviewed": True,
                "confidence": 0.95,
                "publication_date": "2023-06-01",
            },
            {
                "id": str(uuid4()),
                "title": "Study B",
                "source_type": "company_source",
                "study_design": "in_vitro_cell_line",
                "sample_size": 5,
                "peer_reviewed": False,
                "confidence": 0.70,
                "publication_date": "2020-01-01",
            },
        ],
    }
    resp = client.post("/api/v1/decision/evidence/rank", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_candidates"] == 2
    assert data["ranked_evidence"][0]["title"] == "Study A"
    assert data["ranked_evidence"][0]["composite_rank_score"] > data["ranked_evidence"][1]["composite_rank_score"]


def test_migration_042_exists() -> None:
    """Verifies that migration 042 exists."""
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "services" / "kg" / "migrations" / "042_evidence_ranking.sql"

    assert migration_path.exists(), f"Migration not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    assert "evidence_rankings_log" in content
    assert "view_ranked_evidence_overview" in content
    assert "composite_rank_score" in content
    assert "TIER_1_PINNACLE" in content
