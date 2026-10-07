from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.domain.canonical_model import ScientificEvidenceState
from app.opportunity_engine.domain.entity_resolution import CanonicalAssetResolver
from app.opportunity_engine.ingestion.pubmed import (
    ExtractedObservation,
    ExtractionCategory,
    ExtractionLineage,
    IngestionResult,
    IngestionStatus,
    MultiDomainBiomedicalExtractor,
    PubMedArticleRecord,
    PubMedIngestionService,
    PubMedQualityChecker,
)


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


def sample_nature_cancer_article() -> PubMedArticleRecord:
    """Fixture representing the landmark 2024 Nature Cancer Zongertinib publication."""
    return PubMedArticleRecord(
        pmid="38718468",
        doi="10.1038/s43018-024-00778-5",
        title="Selective HER2 oncogenic mutant inhibition by BI 1810631 (Zongertinib) spares wild-type EGFR",
        abstract=(
            "Activating ERBB2 (HER2) kinase domain mutations, including L755S, V777L, and exon 20 insertion "
            "(Y772_A775dup), drive oncogenesis in metastatic breast cancer and NSCLC. Current pan-HER TKIs induce "
            "severe wild-type EGFR-mediated toxicities, limiting therapeutic index. Here, we report that zongertinib "
            "(BI 1810631) is a potent, irreversible covalent inhibitor exhibiting IC50 of 2.4 nM against HER2 mutants "
            "with >59-fold selectivity margin over wild-type EGFR. In Ba/F3 cell line and MCF-7 models, zongertinib "
            "drove deep tumor regression. In BALB/c nude mouse orthotopic brain metastasis models, zongertinib demonstrated "
            "brain-to-plasma ratio of 0.42 and robust intracranial regression. Early clinical cohorts demonstrated confirmed ORR "
            "of 73.8% and median PFS of 12.4 months with Grade >=3 diarrhea of only 3.9%. ER pathway adaptation was identified "
            "as a secondary resistance mechanism, which was successfully reversed in combination with fulvestrant."
        ),
        authors=["Wilding B", "Neumüller R", "Savarese F", "Kopp H", "Wunberg H"],
        journal="Nature Cancer",
        publication_date=date(2024, 5, 8),
        study_type="preclinical_and_early_clinical",
        keywords=["HER2", "Zongertinib", "EGFR", "Exon 20", "Tyrosine Kinase Inhibitor", "Brain Metastases"],
        mesh_terms=["Receptor, ErbB-2", "Protein Kinase Inhibitors", "Breast Neoplasms", "Mutation", "Mice, Nude"],
        mesh=["Receptor, ErbB-2", "Protein Kinase Inhibitors", "Breast Neoplasms", "Mutation", "Mice, Nude"],
        entities=["Zongertinib", "HER2", "EGFR", "L755S", "V777L", "Fulvestrant"],
        references=["PMID:30199738", "PMID:31548725", "PMID:34525330"],
        raw_source={"source": "NCBI PubMed EFetch", "status": "indexed"},
    )


def test_pubmed_article_record_captures_all_required_fields() -> None:
    """
    Verifies that PubMedArticleRecord captures all required fields:
    PMID, title, abstract, authors, journal, publication date, study type,
    MeSH, keywords.
    """
    article = sample_nature_cancer_article()

    # 1. PMID
    assert article.pmid == "38718468"
    # 2. Title
    assert "Zongertinib" in article.title
    # 3. Abstract
    assert "HER2" in article.abstract
    # 4. Authors
    assert len(article.authors) == 5
    assert "Wilding B" in article.authors
    # 5. Journal
    assert article.journal == "Nature Cancer"
    # 6. Publication date
    assert article.publication_date == date(2024, 5, 8)
    # 7. Study type
    assert article.study_type == "preclinical_and_early_clinical"
    # 8. MeSH
    assert len(article.mesh) >= 5
    assert "Receptor, ErbB-2" in article.mesh
    # 9. Keywords
    assert len(article.keywords) >= 5
    assert "Zongertinib" in article.keywords

    # Deduplication hash
    assert len(article.content_hash) == 64


def test_extract_all_twelve_requested_categories() -> None:
    """
    Verifies extraction of all 12 categories requested:
    asset, target, disease, biomarker, mutation, model, efficacy,
    toxicity, CNS, resistance, combination, clinical result.
    """
    article = sample_nature_cancer_article()
    observations = MultiDomainBiomedicalExtractor.extract_from_article(article)
    extracted_categories = {o.extraction_category for o in observations}

    # 1. Asset / Drug
    assert ExtractionCategory.DRUG in extracted_categories or ExtractionCategory.ASSET in extracted_categories
    # 2. Target
    assert ExtractionCategory.TARGET in extracted_categories
    # 3. Disease
    assert ExtractionCategory.DISEASE in extracted_categories
    # 4. Biomarker
    assert ExtractionCategory.BIOMARKER in extracted_categories
    # 5. Mutation
    assert ExtractionCategory.MUTATION in extracted_categories
    # 6. Model (cell lines and animal models)
    assert any(c in extracted_categories for c in (ExtractionCategory.MODEL, ExtractionCategory.CELL_LINE, ExtractionCategory.ANIMAL_MODEL))
    # 7. Efficacy
    assert ExtractionCategory.EFFICACY in extracted_categories
    # 8. Toxicity
    assert ExtractionCategory.TOXICITY in extracted_categories
    # 9. CNS (CNS exposure or CNS efficacy)
    assert any(c in extracted_categories for c in (ExtractionCategory.CNS, ExtractionCategory.CNS_EXPOSURE, ExtractionCategory.CNS_EFFICACY))
    # 10. Resistance
    assert ExtractionCategory.RESISTANCE in extracted_categories
    # 11. Combination
    assert ExtractionCategory.COMBINATION in extracted_categories
    # 12. Clinical result / clinical outcome
    assert any(c in extracted_categories for c in (ExtractionCategory.CLINICAL_RESULT, ExtractionCategory.CLINICAL_OUTCOME))


def test_raw_evidence_storage_and_extraction_lineage() -> None:
    """
    Verifies that raw evidence and complete immutable extraction lineage are stored:
    lineage_id, source location, verbatim raw quote, extractor model/version,
    provenance hash, and evidence source linking.
    """
    article = sample_nature_cancer_article()
    observations = MultiDomainBiomedicalExtractor.extract_from_article(article)

    assert len(observations) > 10

    for obs in observations:
        # Immutable Lineage Verification
        assert obs.lineage is not None
        assert obs.lineage.pmid == "38718468"
        assert obs.lineage.article_title == article.title
        assert obs.lineage.journal == "Nature Cancer"
        assert obs.lineage.extractor_model == "BioExtractor-Ensemble-v2.1"
        assert obs.lineage.source_location.startswith("Sentence ")
        assert len(obs.lineage.raw_verbatim_quote) > 0
        assert len(obs.lineage.provenance_hash) == 64  # SHA-256

        # Critical Safety: Inferences never flagged as ground truth
        assert obs.is_ground_truth is False
        assert obs.epistemic_status == ScientificEvidenceState.AI_INFERENCE
        assert 0.0 <= obs.confidence <= 1.0


def test_automated_quality_checks_and_anti_hallucination() -> None:
    """
    Verifies automated quality checks and anti-hallucination verification:
    - Quality report generation
    - Groundedness check (every extracted quote anchored to source text)
    - Quality scoring and tier assignment
    """
    article = sample_nature_cancer_article()
    observations = MultiDomainBiomedicalExtractor.extract_from_article(article)

    report = PubMedQualityChecker.evaluate_article_quality(article, observations)

    assert report.pmid == "38718468"
    assert report.quality_passed is True
    assert report.quality_tier == "HIGH"
    assert report.overall_quality_score >= 85.0
    assert report.hallucination_check_passed is True
    assert len(report.rules) >= 7

    # Test hallucination detection: Inject an ungrounded hallucinated observation
    hallucinated_obs = list(observations)
    hallucinated_obs.append(
        ExtractedObservation(
            pmid="38718468",
            extraction_category=ExtractionCategory.DRUG,
            entity_text="HallucinatedCompoundXYZ",
            extracted_text="This sentence does not exist anywhere in the article at all.",
            source_location="Sentence 999",
            source_citation="Fabricated",
        )
    )

    bad_report = PubMedQualityChecker.evaluate_article_quality(article, hallucinated_obs)
    assert bad_report.hallucination_check_passed is False
    assert any("ungrounded" in r.details.lower() for r in bad_report.rules if not r.passed)


def test_idempotent_ingestion_and_content_deduplication() -> None:
    """
    Verifies that ingesting the same PMID / content multiple times
    is strictly idempotent and returns DUPLICATE_SKIPPED without duplication.
    """
    service = PubMedIngestionService()
    article = sample_nature_cancer_article()

    import asyncio
    res1 = asyncio.run(service.ingest_article(article))
    assert res1.status == IngestionStatus.INGESTED
    assert res1.is_duplicate is False
    assert res1.observations_count > 0
    assert res1.quality_report is not None
    assert res1.evidence_source_id is not None

    # Second ingestion with identical content
    res2 = asyncio.run(service.ingest_article(article))
    assert res2.status == IngestionStatus.DUPLICATE_SKIPPED
    assert res2.is_duplicate is True
    assert res2.observations_count == res1.observations_count
    assert res2.content_hash == res1.content_hash
    assert res2.evidence_source_id == res1.evidence_source_id

    # Check store contains only 1 entry
    assert len(service.articles_by_pmid) == 1
    assert len(service.articles_by_hash) == 1


def test_retry_handling_on_transient_failures() -> None:
    """
    Verifies exponential backoff retry handling when fetching external data.
    """
    import asyncio
    service = PubMedIngestionService(max_retries=3, backoff_seconds=0.01)
    article = sample_nature_cancer_article()

    attempts = 0

    def transient_flaky_fetcher() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError(f"Transient NCBI gateway timeout on attempt {attempts}")

    res = asyncio.run(service.ingest_article(article, fetcher_fn=transient_flaky_fetcher))
    assert res.status == IngestionStatus.RETRIED_AND_SUCCEEDED
    assert res.retry_count == 2
    assert attempts == 3


def test_retry_handling_exhausts_retries_gracefully() -> None:
    """
    Verifies that permanent failure records a FAILED status with error details.
    """
    import asyncio
    service = PubMedIngestionService(max_retries=2, backoff_seconds=0.01)
    article = sample_nature_cancer_article()

    def permanent_failure() -> None:
        raise TimeoutError("NCBI API permanently down")

    res = asyncio.run(service.ingest_article(article, fetcher_fn=permanent_failure))
    assert res.status == IngestionStatus.FAILED
    assert res.retry_count == 2
    assert "NCBI API permanently down" in (res.error_message or "")


def test_canonical_entity_resolution_on_ingestion() -> None:
    """
    Verifies entity resolution links extracted drug mentions (e.g. BI 1810631 / Zongertinib)
    to canonical assets with confidence and resolution method.
    """
    import asyncio
    resolver = CanonicalAssetResolver()
    service = PubMedIngestionService(resolver=resolver)
    article = sample_nature_cancer_article()

    res = asyncio.run(service.ingest_article(article))
    assert res.resolved_entities_count >= 1

    drug_obs = service.get_observations(article.pmid, category=ExtractionCategory.DRUG)
    assert len(drug_obs) >= 1
    # Zongertinib should be resolved to its canonical asset ID and preferred name
    resolved = [o for o in drug_obs if o.resolved_canonical_id]
    assert len(resolved) >= 1
    assert resolved[0].resolved_canonical_name == "Zongertinib"
    assert resolved[0].entity_resolution_confidence is not None
    assert resolved[0].resolution_method is not None


def test_api_pubmed_ingestion_endpoints(test_client):
    """
    Verifies REST API endpoints:
    - POST /api/v1/ingest/pubmed/article
    - GET /api/v1/ingest/pubmed/{pmid}
    - GET /api/v1/ingest/pubmed/{pmid}/observations
    - GET /api/v1/ingest/pubmed/{pmid}/quality
    - GET /api/v1/ingest/pubmed/{pmid}/lineage
    - POST /api/v1/ingest/pubmed/batch
    """
    article = sample_nature_cancer_article()
    payload = article.model_dump(mode="json")

    # 1. Ingest article
    resp = test_client.post("/api/v1/ingest/pubmed/article?force_reprocess=true", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pmid"] == "38718468"
    assert data["status"] in ("INGESTED", "RETRIED_AND_SUCCEEDED")
    assert data["observations_count"] > 0
    assert "quality_report" in data
    assert data["quality_report"]["quality_passed"] is True

    # 2. Get article by PMID
    resp_art = test_client.get("/api/v1/ingest/pubmed/38718468")
    assert resp_art.status_code == 200
    assert resp_art.json()["title"] == article.title

    # 3. Get observations with category filter
    resp_obs = test_client.get("/api/v1/ingest/pubmed/38718468/observations?category=cns")
    assert resp_obs.status_code == 200
    cns_obs = resp_obs.json()
    assert len(cns_obs) >= 1

    # 4. Get quality report
    resp_q = test_client.get("/api/v1/ingest/pubmed/38718468/quality")
    assert resp_q.status_code == 200
    assert resp_q.json()["quality_tier"] == "HIGH"

    # 5. Get extraction lineage
    resp_lin = test_client.get("/api/v1/ingest/pubmed/38718468/lineage")
    assert resp_lin.status_code == 200
    lin_data = resp_lin.json()
    assert lin_data["total_observations"] > 0
    assert len(lin_data["lineage_records"]) > 0
    first_lin = lin_data["lineage_records"][0]
    assert "lineage" in first_lin
    assert first_lin["lineage"]["extractor_model"] == "BioExtractor-Ensemble-v2.1"

    # 6. Batch ingestion
    batch_payload = {
        "articles": [payload],
        "force_reprocess": False,
        "run_quality_checks": True,
    }
    resp_batch = test_client.post("/api/v1/ingest/pubmed/batch", json=batch_payload)
    assert resp_batch.status_code == 200
    assert resp_batch.json()["total_submitted"] == 1


def test_migration_016_exists() -> None:
    """Verifies that 016_pubmed_ingestion.sql exists and creates required tables."""
    migration_path = Path("services/kg/migrations/016_pubmed_ingestion.sql")
    assert migration_path.exists(), "Migration 016_pubmed_ingestion.sql missing"
    content = migration_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS pubmed_raw_articles" in content
    assert "CREATE TABLE IF NOT EXISTS pubmed_extracted_observations" in content
    assert "CREATE TABLE IF NOT EXISTS pubmed_ingestion_audit_logs" in content
    assert "idx_pubmed_raw_pmid" in content
    assert "idx_pubmed_obs_category" in content
