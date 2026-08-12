from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.connectors.base import BaseConnector
from app.connectors.factory import ConnectorFactory
from app.connectors.sources import CompanyWebsiteConnector, PatentsConnector
from app.database.models import IngestionJobState, job_store
from app.integrations.kg_client import KGClient
from app.integrations.wiki_client import LLMWikiClient
from app.main import app
from app.nlp.deduplication import DuplicateDetector
from app.nlp.evidence_ranking import EvidenceRanker
from app.nlp.ner import RuleBasedEntityExtractor
from app.nlp.pipeline import LiteratureNLP
from app.nlp.relationships import RelationshipExtractor
from app.nlp.summarizer import DocumentSummarizer
from app.orchestrator.pipeline import PipelineRunner
from app.parsing.text_parser import TextParser

client = TestClient(app)


def test_all_11_connectors_registered_and_instantiated():
    required_sources = [
        "pubmed",
        "pmc",
        "clinicaltrials",
        "aacr",
        "asco",
        "sabcs",
        "esmo",
        "biorxiv",
        "medrxiv",
        "patents",
        "company_websites",
    ]

    for source in required_sources:
        connector = ConnectorFactory.create(source, {"timeout": 0.1})
        assert connector.name == source
        info = connector.connect()
        assert info["connected"] is True
        fetched = connector.fetch("HER2 breast cancer")
        assert isinstance(fetched, list)
        if fetched:
            assert "title" in fetched[0]
            assert "source" in fetched[0]
        else:
            assert connector.get_limitation() is not None or source in {"pubmed", "pmc", "clinicaltrials", "biorxiv", "medrxiv"}


def test_connectors_with_documented_limitations():
    limitation_sources = ["aacr", "asco", "sabcs", "esmo", "patents", "company_websites"]
    for source in limitation_sources:
        connector = ConnectorFactory.create(source)
        limitation = connector.get_limitation()
        assert limitation is not None
        assert isinstance(limitation, str)


def test_conference_connectors_return_search_metadata(monkeypatch):
    search_html = """
        <html><head><title>Test Search</title><meta name='description' content='Conference results'></head>
        <body><a href='/article/123'>Result</a></body></html>
    """
    detail_html = """
        <html><head><title>Detail Page</title><meta name='description' content='Detail abstract'></head>
        <body><p>Full content here.</p></body></html>
    """

    def fake_request_text(self, url, **kwargs):
        if url.endswith("/search-results?q=test") or "action/doSearch" in url or "?s=test" in url or "search?searchText=test" in url:
            return search_html
        return detail_html

    monkeypatch.setattr(BaseConnector, "_request_text", fake_request_text)

    for source in ["aacr", "asco", "sabcs", "esmo"]:
        connector = ConnectorFactory.create(source)
        results = connector.fetch("test", max_results=1)
        assert isinstance(results, list)
        assert len(results) == 1
        item = results[0]
        assert item["source"] == source
        assert item["url"] is not None
        assert item["metadata"]["limitation"] == connector.get_limitation()


def test_patents_connector_falls_back_to_search_page(monkeypatch):
    search_html = """
        <html><head><title>Patent search</title><meta name='description' content='Patent results'></head>
        <body><p>Patent listing content.</p></body></html>
    """

    def fake_request_json(self, url, **kwargs):
        return {"patents": []}

    def fake_request_text(self, url, **kwargs):
        return search_html

    monkeypatch.setattr(PatentsConnector, "_request_json", fake_request_json)
    monkeypatch.setattr(PatentsConnector, "_request_text", fake_request_text)

    connector = PatentsConnector()
    results = connector.fetch("cancer", max_results=1)
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["source"] == "patents"
    assert results[0]["metadata"]["limitation"] == connector.get_limitation()


def test_company_website_connector_crawls_configured_urls(monkeypatch):
    urls = ["https://example.com/press"]
    html = """
        <html><head><title>Press Release</title><meta name='description' content='New data'></head>
        <body><p>Launch announcement with trastuzumab.</p></body></html>
    """

    class FakeCrawlResult:
        def __init__(self, url, html):
            self.url = url
            self.success = True
            self.status_code = 200
            self.error = None
            self.metadata = {"title": "Press Release", "content": html}
            self.html = html

    def fake_crawl(self, seed_urls):
        return [FakeCrawlResult(seed_urls[0], html)]

    monkeypatch.setattr("app.crawling.crawler.WebCrawler.crawl", fake_crawl)

    connector = CompanyWebsiteConnector({"urls": urls})
    results = connector.fetch("trastuzumab", max_results=1)
    assert isinstance(results, list)
    assert len(results) == 1
    item = results[0]
    assert item["source"] == "company_websites"
    assert item["metadata"]["limitation"] == connector.get_limitation()


def test_connector_retry_behavior(monkeypatch):
    connector = ConnectorFactory.create("pubmed", {"timeout": 0.1, "max_retries": 1, "backoff_seconds": 0.0})
    attempts = {"count": 0}

    def flaky_request(self, method, url, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ReadTimeout("temporary timeout")
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"esearchresult": {"idlist": []}}
        return response

    monkeypatch.setattr(httpx.Client, "request", flaky_request)
    assert connector.fetch("HER2") == []
    assert attempts["count"] == 2


def test_parser_strips_html_and_handles_malformed_metadata():
    parser = TextParser()
    raw_doc = {
        "title": "<h1>HER2 Therapy</h1>",
        "abstract": "<p>Trastuzumab shows <b>efficacy</b>.</p>",
        "authors": "Alice Smith, Bob Jones",
        "metadata": "not_a_dict",  # malformed
    }
    normalized = parser.normalize_document(raw_doc)
    assert normalized["title"] == "HER2 Therapy"
    assert normalized["abstract"] == "Trastuzumab shows efficacy."
    assert normalized["authors"] == ["Alice Smith", "Bob Jones"]
    assert isinstance(normalized["metadata"], dict)


def test_ner_extracts_entities_across_categories():
    extractor = RuleBasedEntityExtractor()
    text = "Trastuzumab targets HER2 protein in breast cancer clinical trial NCT01234567 conducted by AACR."
    entities = extractor.extract_entities(text)
    labels = {e["label"] for e in entities}
    assert "drug" in labels
    assert "gene" in labels or "protein" in labels
    assert "disease" in labels
    assert "clinical_trial" in labels
    assert "organization" in labels


def test_summarizer_extractive_fallback():
    summarizer = DocumentSummarizer()
    doc = {
        "title": "HER2 Targeted Therapy in Breast Cancer",
        "abstract": "Trastuzumab significantly improves progression-free survival in patients with HER2-positive breast cancer. Overall response rates were high.",
    }
    summary = summarizer.summarize(doc)
    assert summary["summary_type"] == "extractive_fallback"
    assert "Trastuzumab" in summary["concise_summary"]
    assert summary["llm_used"] is False


def test_spacy_provider_falls_back_to_rule_based(monkeypatch):
    def fake_init(self, model_name="en_core_web_sm"):
        self.available = False
        self.nlp = None

    monkeypatch.setattr(
        "app.nlp.ner.SpaCyEntityExtractor.__init__",
        fake_init,
    )

    nlp = LiteratureNLP({"ner_provider": "spacy"})
    assert isinstance(nlp.ner, RuleBasedEntityExtractor)


def test_summarizer_llm_fallback_retries_and_uses_extractive(monkeypatch):
    summarizer = DocumentSummarizer(
        {
            "llm_api_key": "fake-key",
            "llm_api_url": "http://invalid-llm",
            "llm_max_retries": 1,
            "llm_backoff_seconds": 0.0,
        }
    )

    def always_fail(*args, **kwargs):
        raise httpx.HTTPError("LLM service unavailable")

    monkeypatch.setattr(httpx, "post", always_fail)

    doc = {
        "title": "HER2 Targeted Therapy in Breast Cancer",
        "abstract": "Trastuzumab significantly improves progression-free survival in patients with HER2-positive breast cancer.",
    }
    summary = summarizer.summarize(doc)
    assert summary["summary_type"] == "extractive_fallback"
    assert summary["llm_used"] is False


def test_relationship_extraction():
    extractor = RelationshipExtractor()
    doc = {
        "title": "Trastuzumab clinical trial",
        "abstract": "Trastuzumab targets HER2 and treats breast cancer.",
        "source_id": "PMID999",
    }
    entities = [
        {"text": "trastuzumab", "label": "drug", "category": "drugs"},
        {"text": "her2", "label": "gene", "category": "genes"},
        {"text": "breast cancer", "label": "disease", "category": "diseases"},
    ]
    relationships = extractor.extract(doc, entities)
    predicates = [r["predicate"] for r in relationships]
    assert "targets" in predicates
    assert "treats" in predicates


def test_duplicate_detection_four_tiers():
    detector = DuplicateDetector()

    # Tier 1: DOI
    d1 = detector.detect_duplicate({"doi": "10.1000/a"}, {"doi": "10.1000/a"})
    assert d1["duplicate"] is True and d1["reason"] == "doi_match"

    # Tier 2: Source ID
    d2 = detector.detect_duplicate({"source": "pubmed", "source_id": "123"}, {"source": "pubmed", "source_id": "123"})
    assert d2["duplicate"] is True and d2["reason"] == "source_id_match"

    # Tier 3: Title
    d3 = detector.detect_duplicate({"title": "Breast Cancer Study!"}, {"title": "breast cancer study"})
    assert d3["duplicate"] is True and d3["reason"] == "title_match"

    # Tier 4: Content Hash
    d4 = detector.detect_duplicate({"abstract": "Unique content string for testing hashing"}, {"content": "Unique content string for testing hashing"})
    assert d4["duplicate"] is True and d4["reason"] == "content_hash_match"

    # Distinct
    d5 = detector.detect_duplicate({"title": "Paper A"}, {"title": "Paper B"})
    assert d5["duplicate"] is False


def test_evidence_ranking_deterministic_scoring():
    ranker = EvidenceRanker()
    high_doc = {
        "source": "clinicaltrials",
        "title": "Phase 3 Clinical Trial of Trastuzumab",
        "published_date": "2024-01-01",
        "metadata": {"overallStatus": "Completed"},
    }
    low_doc = {
        "source": "biorxiv",
        "title": "Preprint abstract",
        "published_date": "2015-01-01",
    }
    high_rank = ranker.rank_document(high_doc)
    low_rank = ranker.rank_document(low_doc)

    assert high_rank["score"] > low_rank["score"]
    assert high_rank["tier"] in ("High", "Medium")


def test_kg_integration_success_and_graceful_failure():
    kg_client = KGClient({"kg_service_url": "http://invalid-localhost-9999"})
    entities = [{"text": "trastuzumab", "label": "drug", "category": "drugs"}]
    relationships = [{"subject": "trastuzumab", "predicate": "targets", "object": "her2"}]

    res = kg_client.update_knowledge_graph(entities, relationships)
    assert res["success"] is False
    assert res["retry_eligible"] is True

    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        valid_client = KGClient({"kg_service_url": "http://localhost:8001"})
        res_ok = valid_client.update_knowledge_graph(entities, relationships)
        assert res_ok["success"] is True


def test_wiki_integration_okf_volume_write(tmp_path):
    wiki_client = LLMWikiClient({"wiki_dir": str(tmp_path)})
    doc = {"source": "pubmed", "source_id": "PMID123", "title": "HER2 Study", "doi": "10.1000/xyz", "url": "https://example.com"}
    entities = [{"text": "her2", "category": "genes"}]
    summary = {"concise_summary": "HER2 targeted therapy."}

    res = wiki_client.update_wiki(doc, entities, summary)
    assert res["success"] is True
    assert res["method"] == "okf_volume"

    concept_file = tmp_path / "wiki" / "genes" / "her2.md"
    assert concept_file.exists()
    assert "HER2 Study" in concept_file.read_text(encoding="utf-8")


def test_orchestrator_state_transitions_and_dead_letter():
    job = IngestionJobState(id="job-test-1", source="pubmed", query="oncology")
    job_store.save(job)

    def failing_stage(payload):
        raise ValueError("Stage failure simulation")

    runner = PipelineRunner(stages=[failing_stage], retries=1, delay_seconds=0.01)
    result = runner.run_with_job(job, {"query": "oncology"})

    assert result["status"] == "dead_letter"
    updated_job = job_store.get("job-test-1")
    assert updated_job.status == "dead_letter"
    assert "Stage failure simulation" in updated_job.error


def test_end_to_end_ingestion_api():
    response = client.post("/api/v1/ingestion", json={"source": "pubmed", "query": "trastuzumab HER2"})
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["status"] in ("completed", "pending", "running")

    job_res = client.get(f"/api/v1/ingestion/{data['id']}")
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["status"] == "completed"
    assert "result" in job_data
    assert "source_status" in job_data["result"]
