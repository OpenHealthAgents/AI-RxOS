from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors.base import BaseConnector
from app.connectors.factory import ConnectorFactory
from app.connectors.sources import CompanyWebsiteConnector, PatentsConnector, PubMedConnector
from app.database.models import IngestionJobState, job_store
from app.integrations.kg_client import KGClient
from app.integrations.wiki_client import LLMWikiClient
from app.main import app
from app.knowledge.models import TenantContext
from app.routers.papers import get_paper
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
        assert callable(connector.connect)
        assert callable(connector.fetch)


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


def test_pubmed_efetch_preserves_structured_metadata_and_paginates(monkeypatch):
    connector = PubMedConnector({"requests_per_second": 0, "max_retries": 0})

    xml = """<PubmedArticleSet><PubmedArticle>
      <MedlineCitation><PMID>12345</PMID><Article>
        <ArticleTitle>Targeted therapy study</ArticleTitle>
        <Abstract><AbstractText Label="BACKGROUND">First section.</AbstractText>
          <AbstractText Label="RESULTS">Second section.</AbstractText></Abstract>
        <AuthorList><Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName>
          <Identifier Source="ORCID">0000-0000-0000-0001</Identifier>
          <AffiliationInfo><Affiliation>Example University</Affiliation></AffiliationInfo>
        </Author></AuthorList>
        <Journal><Title>Journal of Tests</Title><JournalIssue><PubDate><Year>2019</Year><Month>Jun</Month></PubDate></JournalIssue></Journal>
        <Language>eng</Language><PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
        <ArticleDate DateType="Electronic"><Year>2019</Year><Month>5</Month></ArticleDate>
        <KeywordList><Keyword>oncology</Keyword></KeywordList>
        <MeshHeadingList><MeshHeading><DescriptorName MajorTopicYN="Y">Neoplasms</DescriptorName></MeshHeading></MeshHeadingList>
        <ChemicalList><Chemical><NameOfSubstance UI="D000001">Example compound</NameOfSubstance><RegistryNumber>0</RegistryNumber></Chemical></ChemicalList>
        <GrantList><Grant><GrantID>G1</GrantID><Agency>Example</Agency></Grant></GrantList>
      </Article></MedlineCitation><PubmedData><ArticleIdList>
        <ArticleId IdType="pubmed">12345</ArticleId><ArticleId IdType="pmc">PMC98765</ArticleId>
        <ArticleId IdType="doi">10.1000/example</ArticleId>
      </ArticleIdList></PubmedData>
    </PubmedArticle></PubmedArticleSet>"""

    class Response:
        def __init__(self, text="", payload=None):
            self.text = text
            self.payload = payload

        def json(self):
            return self.payload

    def request(method, url, **kwargs):
        if url.endswith("esearch.fcgi"):
            return Response(payload={"esearchresult": {"idlist": ["12345"], "count": "2"}})
        return Response(text=xml)

    monkeypatch.setattr(connector, "_request", request)
    records, next_token = connector.fetch_page("breast cancer", page_size=1)

    assert next_token == "1"
    assert len(records) == 1
    record = records[0]
    assert record["source_id"] == "PMID:12345"
    assert record["pmid"] == "12345"
    assert record["pmcid"] == "PMC98765"
    assert record["doi"] == "10.1000/example"
    assert record["abstract"] == "BACKGROUND: First section.\nRESULTS: Second section."
    assert record["publication_date"] == "2019 Jun"
    assert record["metadata"]["authors"][0]["identifiers"][0]["value"] == "0000-0000-0000-0001"
    assert record["metadata"]["affiliations"] == ["Example University"]
    assert record["metadata"]["mesh_terms"][0]["descriptor"] == "Neoplasms"
    assert record["metadata"]["grants"][0]["grant_id"] == "G1"
    assert record["metadata"]["article_dates"] == [{"date_type": "Electronic", "source_precision": "2019 5"}]
    assert record["metadata"]["chemicals"][0]["name"] == "Example compound"
    assert record["metadata"]["chemicals"][0]["registry_number"] == "0"
    assert record["metadata"]["journal_issue"]["volume"] is None
    assert "raw_xml" in record["metadata"]
    assert len(record["metadata"]["content_hash"]) == 64


def test_pubmed_record_with_missing_optional_fields_keeps_unknowns_null(monkeypatch):
    connector = PubMedConnector({"requests_per_second": 0, "max_retries": 0})

    class Response:
        text = "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>54321</PMID><Article><ArticleTitle>Source title</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"

        def json(self):
            return {"esearchresult": {"idlist": ["54321"], "count": "1"}}

    monkeypatch.setattr(connector, "_request", lambda *args, **kwargs: Response())
    records, next_token = connector.fetch_page("54321[uid]")

    assert next_token is None
    assert len(records) == 1
    assert records[0]["title"] == "Source title"
    assert records[0]["abstract"] is None
    assert records[0]["authors"] == []
    assert records[0]["publication_date"] is None
    assert records[0]["doi"] is None


@pytest.mark.asyncio
async def test_paper_detail_exposes_pubmed_provenance_and_temporal_fields(monkeypatch):
    retrieved_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    ingested_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
    row = {
        "id": str(uuid4()),
        "title": "A PubMed paper",
        "source": "pubmed",
        "doi": "10.1000/example",
        "published_at": None,
        "citation_count": 0,
        "pmid": "12345",
        "pmcid": "PMC12345",
        "abstract": "Abstract text",
        "authors": '[{"last_name":"Lovelace"}]',
        "journal": "Journal of Tests",
        "source_id": "PMID:12345",
        "publication_date_source": "2019 Jun",
        "retrieved_at": retrieved_at,
        "ingested_at": ingested_at,
        "source_metadata": '{"raw_xml":"<article/>","parser":"fixture"}',
        "extracted_entities": '[{"text":"HER2","type":"gene"}]',
        "extracted_relationships": "[]",
        "canonical_entity_id": "11111111-1111-1111-1111-111111111111",
        "reconciliation_status": "EXACT_MATCH",
    }

    class FakeConnection:
        async def fetchrow(self, query, paper_id):
            return row

    class FakeDatabase:
        pool = object()

        @asynccontextmanager
        async def acquire(self, organization_id=None):
            yield FakeConnection()

    monkeypatch.setattr("app.routers.papers.postgres_manager", FakeDatabase())
    paper = await get_paper(UUID(row["id"]), TenantContext())

    assert paper.pmid == "12345"
    assert paper.pmcid == "PMC12345"
    assert paper.publication_date_source == "2019 Jun"
    assert paper.published_at is None
    assert paper.retrieved_at == retrieved_at
    assert paper.ingested_at == ingested_at
    assert paper.source_metadata["raw_xml"] == "<article/>"
    assert paper.extracted_entities[0]["text"] == "HER2"
    assert paper.reconciliation_status == "EXACT_MATCH"


def test_pubmed_search_failure_propagates_after_bounded_retries(monkeypatch):
    connector = PubMedConnector({"requests_per_second": 0, "max_retries": 0})

    def fail_request(*args, **kwargs):
        raise httpx.ConnectError("NCBI unavailable")

    monkeypatch.setattr(connector, "_request", fail_request)
    with pytest.raises(httpx.ConnectError):
        connector.fetch_page("breast cancer")


def test_pubmed_rate_limit_response_uses_bounded_http_retry(monkeypatch):
    connector = PubMedConnector({
        "requests_per_second": 0,
        "max_retries": 1,
        "backoff_seconds": 0.25,
    })
    request = httpx.Request("GET", "https://ncbi.example/esearch.fcgi")
    responses = [
        httpx.Response(429, request=request),
        httpx.Response(200, request=request),
    ]
    delays = []

    def request_once(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(httpx.Client, "request", request_once)
    monkeypatch.setattr("app.connectors.base.time.sleep", delays.append)
    response = connector._request("GET", str(request.url))

    assert response.status_code == 200
    assert delays == [0.25]


def test_pubmed_accepts_a_deterministic_pmid_set_without_rewriting_query(monkeypatch):
    connector = PubMedConnector({"requests_per_second": 0, "max_retries": 0})
    observed_params = []

    class Response:
        def json(self):
            return {"esearchresult": {"idlist": [], "count": "0"}}

    def request(method, url, **kwargs):
        observed_params.append(kwargs["params"])
        return Response()

    monkeypatch.setattr(connector, "_request", request)
    pmid_query = "12345[PMID] OR 67890[PMID]"

    records, next_token = connector.fetch_page(pmid_query)

    assert records == []
    assert next_token is None
    assert observed_params[0]["term"] == pmid_query


def test_pubmed_connector_paces_ncbi_requests(monkeypatch):
    import app.connectors.sources as pubmed_module

    connector = PubMedConnector({"requests_per_second": 2})
    times = iter([10.0, 10.1, 10.5])
    delays = []
    monkeypatch.setattr(pubmed_module, "_PUBMED_LAST_REQUEST", 0.0)
    monkeypatch.setattr(pubmed_module.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(pubmed_module.time, "sleep", delays.append)
    monkeypatch.setattr(BaseConnector, "_request", lambda self, method, url, **kwargs: "ok")

    assert connector._request("GET", "https://ncbi.example/search") == "ok"
    assert connector._request("GET", "https://ncbi.example/fetch") == "ok"
    assert len(delays) == 1
    assert abs(delays[0] - 0.4) < 0.000001


@pytest.mark.asyncio
async def test_kg_client_sends_pubmed_record_to_canonical_endpoint(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"canonical_entity_id": "entity-1", "claim_id": "claim-1"}

    class Client:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json, headers):
            captured.update(url=url, payload=json, headers=headers)
            return Response()

    monkeypatch.setattr("app.integrations.kg_client.httpx.AsyncClient", Client)
    client = KGClient({"kg_service_url": "http://kg.test", "kg_max_retries": 0})
    result = await client.ingest_pubmed_article(
        {"pmid": "12345"}, bearer_token="scoped-signed-token"
    )

    assert result["canonical_entity_id"] == "entity-1"
    assert captured["url"] == "http://kg.test/api/v1/canonical/pubmed/ingest"
    assert captured["payload"] == {"pmid": "12345"}
    assert captured["headers"] == {"Authorization": "Bearer scoped-signed-token"}


@pytest.mark.asyncio
async def test_kg_pubmed_client_retries_transient_status_but_not_permanent_4xx(monkeypatch):
    from app.integrations.kg_client import KGClient

    statuses = [503, 200]
    attempts = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("POST", "http://kg.test/canonical/pubmed/ingest")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("failed", request=request, response=response)

        def json(self):
            return {"canonical_entity_id": "entity-1"}

    class Client:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            attempts.append(1)
            return Response(statuses.pop(0))

    monkeypatch.setattr("app.integrations.kg_client.httpx.AsyncClient", Client)
    monkeypatch.setattr("app.integrations.kg_client.asyncio.sleep", AsyncMock())
    result = await KGClient({"kg_max_retries": 1, "kg_backoff_seconds": 0}).ingest_pubmed_article(
        {"pmid": "12345"}, bearer_token="token"
    )
    assert result["canonical_entity_id"] == "entity-1"
    assert len(attempts) == 2

    statuses[:] = [403]
    attempts.clear()
    with pytest.raises(RuntimeError, match="rejected"):
        await KGClient({"kg_max_retries": 3, "kg_backoff_seconds": 0}).ingest_pubmed_article(
            {"pmid": "12345"}, bearer_token="token"
        )
    assert len(attempts) == 1


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
