from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest

from app.opportunity_engine.domain.canonical_model import ScientificEvidenceState
from app.opportunity_engine.domain.entity_resolution import CanonicalAssetResolver
from app.opportunity_engine.ingestion.pubmed import (
    ExtractedObservation,
    ExtractionCategory,
    IngestionResult,
    IngestionStatus,
    MultiDomainBiomedicalExtractor,
    PubMedArticleRecord,
    PubMedIngestionService,
)


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
        entities=["Zongertinib", "HER2", "EGFR", "L755S", "V777L", "Fulvestrant"],
        references=["PMID:30199738", "PMID:31548725", "PMID:34525330"],
        raw_source={"source": "NCBI PubMed EFetch", "status": "indexed"},
    )


def test_pubmed_article_record_captures_all_required_fields() -> None:
    """
    Verifies that PubMedArticleRecord captures all 11 required fields:
    PMID, title, abstract, authors, journal, publication date, study type,
    keywords, mesh terms, entities, references where available.
    """
    article = sample_nature_cancer_article()

    assert article.pmid == "38718468"
    assert article.doi == "10.1038/s43018-024-00778-5"
    assert "Zongertinib" in article.title
    assert "HER2" in article.abstract
    assert len(article.authors) == 5
    assert article.journal == "Nature Cancer"
    assert article.publication_date == date(2024, 5, 8)
    assert article.study_type == "preclinical_and_early_clinical"
    assert len(article.keywords) >= 5
    assert len(article.mesh_terms) >= 5
    assert len(article.entities) >= 5
    assert len(article.references) == 3
    assert len(article.content_hash) == 64  # SHA-256
    assert "PMID:38718468" in article.source_citation


def test_extraction_pipelines_all_sixteen_categories() -> None:
    """
    Verifies extraction pipelines across all 16 target categories:
    1. drug
    2. target
    3. gene
    4. mutation
    5. disease
    6. biomarker
    7. model
    8. cell line
    9. animal model
    10. efficacy
    11. toxicity
    12. CNS exposure
    13. CNS efficacy
    14. resistance
    15. combination
    16. clinical outcome
    """
    article = sample_nature_cancer_article()
    observations = MultiDomainBiomedicalExtractor.extract_from_article(article)

    extracted_categories = {o.extraction_category for o in observations}

    # Verify that all 16 categories are represented in extraction results
    assert ExtractionCategory.DRUG in extracted_categories
    assert ExtractionCategory.TARGET in extracted_categories
    assert ExtractionCategory.GENE in extracted_categories
    assert ExtractionCategory.MUTATION in extracted_categories
    assert ExtractionCategory.DISEASE in extracted_categories
    assert ExtractionCategory.BIOMARKER in extracted_categories
    assert ExtractionCategory.MODEL in extracted_categories
    assert ExtractionCategory.CELL_LINE in extracted_categories
    assert ExtractionCategory.ANIMAL_MODEL in extracted_categories
    assert ExtractionCategory.EFFICACY in extracted_categories
    assert ExtractionCategory.TOXICITY in extracted_categories
    assert ExtractionCategory.CNS_EXPOSURE in extracted_categories
    assert ExtractionCategory.CNS_EFFICACY in extracted_categories
    assert ExtractionCategory.RESISTANCE in extracted_categories
    assert ExtractionCategory.COMBINATION in extracted_categories
    assert ExtractionCategory.CLINICAL_OUTCOME in extracted_categories


def test_ai_extractions_never_treated_as_ground_truth() -> None:
    """
    CRITICAL SAFETY REQUIREMENT:
    Do not treat LLM extraction as ground truth.
    Store:
    - raw source
    - extracted observation
    - confidence
    - source citation
    - extraction model/version
    """
    article = sample_nature_cancer_article()
    observations = MultiDomainBiomedicalExtractor.extract_from_article(article)

    assert len(observations) > 10

    for obs in observations:
        # Must NEVER be flagged as ground truth
        assert obs.is_ground_truth is False, f"Observation {obs.id} inappropriately marked as ground truth!"
        assert obs.epistemic_status == ScientificEvidenceState.AI_INFERENCE
        assert 0.0 <= obs.confidence <= 1.0
        assert obs.extraction_model_version == "BioExtractor-Ensemble-v2.1"
        assert obs.source_citation.startswith("Wilding B et al., Nature Cancer (2024)")
        assert obs.source_location.startswith("Sentence ")
        assert len(obs.extracted_text) > 0


def test_idempotent_ingestion_and_content_deduplication() -> None:
    """
    Verifies that ingesting the same PMID / content multiple times
    is strictly idempotent and returns DUPLICATE_SKIPPED without duplication.
    """
    service = PubMedIngestionService()
    article = sample_nature_cancer_article()

    # First ingestion
    import asyncio
    res1 = asyncio.run(service.ingest_article(article))
    assert res1.status == IngestionStatus.INGESTED
    assert res1.is_duplicate is False
    assert res1.observations_count > 0

    # Second ingestion with identical content
    res2 = asyncio.run(service.ingest_article(article))
    assert res2.status == IngestionStatus.DUPLICATE_SKIPPED
    assert res2.is_duplicate is True
    assert res2.observations_count == res1.observations_count
    assert res2.content_hash == res1.content_hash

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
    to canonical assets.
    """
    import asyncio
    resolver = CanonicalAssetResolver()
    service = PubMedIngestionService(resolver=resolver)
    article = sample_nature_cancer_article()

    res = asyncio.run(service.ingest_article(article))
    assert res.resolved_entities_count >= 1

    drug_obs = service.get_observations(article.pmid, category=ExtractionCategory.DRUG)
    assert len(drug_obs) >= 1
    # Zongertinib should be resolved to its canonical asset ID
    resolved_ids = [o.resolved_canonical_id for o in drug_obs if o.resolved_canonical_id]
    assert len(resolved_ids) >= 1
    assert resolved_ids[0] is not None


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
