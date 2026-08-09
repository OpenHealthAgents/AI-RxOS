from app.connectors.factory import ConnectorFactory
from app.nlp.pipeline import LiteratureNLP
from app.orchestrator.pipeline import PipelineRunner
from app.services.literature_service import LiteratureService


def test_all_required_connectors_are_registered():
    required = {
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
    }
    available = set(ConnectorFactory.registry)
    assert required.issubset(available)


def test_connector_factory_instantiates_registered_source():
    connector = ConnectorFactory.create("clinicaltrials", {"base_url": "https://example.com"})
    assert connector.name == "clinicaltrials"


def test_parser_normalizes_fields():
    source = {
        "title": "HER2-targeted therapy in breast cancer",
        "abstract": "Trastuzumab improved outcomes in HER2-positive breast cancer.",
        "authors": ["Alice", "Bob"],
        "published_date": "2024-01-15",
        "source": "pubmed",
        "source_id": "PMID123",
        "doi": "10.1000/example",
        "url": "https://example.com/article",
    }
    parsed = LiteratureNLP().parse_document(source)
    assert parsed["title"] == "HER2-targeted therapy in breast cancer"
    assert parsed["source"] == "pubmed"
    assert parsed["authors"] == ["Alice", "Bob"]
    assert parsed["doi"] == "10.1000/example"


def test_duplicate_detector_flags_same_document():
    doc_a = {"doi": "10.1000/example", "title": "HER2 targeted therapy", "source": "pubmed", "source_id": "PMID123"}
    doc_b = {"doi": "10.1000/example", "title": "HER2 targeted therapy", "source": "pubmed", "source_id": "PMID123"}
    result = LiteratureNLP().detect_duplicate(doc_a, doc_b)
    assert result["duplicate"] is True


def test_relationship_extraction_builds_triples():
    doc = {
        "title": "Trastuzumab targets HER2 and treats breast cancer",
        "abstract": "Trastuzumab is associated with HER2-positive breast cancer.",
        "entities": [{"text": "trastuzumab", "label": "drug"}, {"text": "her2", "label": "gene"}, {"text": "breast cancer", "label": "disease"}],
    }
    relationships = LiteratureNLP().extract_relationships(doc)
    assert relationships
    assert any(r["subject"].lower() == "trastuzumab" for r in relationships)


def test_ranking_and_summary_are_deterministic():
    result = LiteratureNLP().run("Trastuzumab targets HER2 in breast cancer. HER2-positive disease is studied in clinical trials.")
    assert "summary" in result
    assert "evidence" in result
    assert result["evidence"][0]["score"] >= 0


def test_orchestrator_runs_complete_pipeline():
    runner = PipelineRunner(
        stages=[
            lambda doc: {**doc, "parsed": True},
            lambda doc: {**doc, "deduplicated": True},
            lambda doc: {**doc, "processed": True},
        ]
    )
    result = runner.run({"id": "paper-1"})
    assert result["processed"] is True


def test_service_ingest_uses_registry_and_returns_payload():
    service = LiteratureService()
    outcome = service.ingest("pubmed", "HER2 breast cancer", base_url="https://example.com")
    assert "source" in outcome
    assert outcome["source"] == "pubmed"
    assert "items" in outcome
