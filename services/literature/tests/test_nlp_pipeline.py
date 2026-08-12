import pytest

from app.nlp.embedding_service import EmbeddingService
from app.nlp.entity_extractor import EntityExtractor
from app.nlp.pipeline import BiomedicalNLPPipeline, process_document
from app.nlp.sentence_segmenter import SentenceSegmenter
from app.nlp.tokenizer import BiomedicalTokenizer
from app.services.search_integration import SearchIntegrationService


def make_doc():
    return {
        "document_id": "doc-001",
        "title": "Test",
        "authors": ["Alice Smith"],
        "abstract": "TP53 p.V600E is observed in many cancer cases. Aspirin may help.",
        "sections": [{"title": "Methods", "text": "EGFR mutations are linked to cancer."}],
    }


def test_sentence_segmentation():
    segmenter = SentenceSegmenter()
    sentences = segmenter.segment("First sentence. Second sentence! Third sentence?")
    assert sentences == ["First sentence.", "Second sentence!", "Third sentence?"]


def test_tokenization():
    tokenizer = BiomedicalTokenizer()
    tokens = tokenizer.tokenize("TP53 p.V600E is observed in cancer.")
    assert tokens[0] == "TP53"
    assert "p.V600E" in tokens
    assert "cancer" in tokens


def test_entity_extraction():
    extractor = EntityExtractor()
    entities = extractor.extract("TP53 p.V600E is observed in cancer and aspirin helps.")
    labels = {entity["type"] for entity in entities}
    assert "gene" in labels
    assert "variant" in labels
    assert "disease" in labels
    assert "drug" in labels


def test_normalization_and_ontology_mapping():
    pipeline = BiomedicalNLPPipeline()
    result = pipeline.process_document(make_doc())

    assert result["document_id"] == "doc-001"
    assert result["sentences"]
    assert result["tokens"]
    assert result["detected_entities"]
    assert result["processing_metadata"]["input_text_length"] > 0
    assert result["execution_metrics"]["total_processing_time_ms"] >= 0

    entity = next(entity for entity in result["detected_entities"] if entity["normalized_identifier"])
    assert entity["ontology_source"] in {"HGNC", "HGVS", "MONDO", "ChEBI"}
    assert 0 <= entity["confidence_score"] <= 1


def test_malformed_input_is_handled_gracefully():
    pipeline = BiomedicalNLPPipeline()
    result = pipeline.process_document({"abstract": None, "sections": "invalid"})
    assert result["sentences"] == []
    assert result["tokens"] == []
    assert result["detected_entities"] == []
    assert result["processing_metadata"]["warnings"]


def test_empty_documents_are_handled():
    pipeline = BiomedicalNLPPipeline()
    result = pipeline.process_document({"abstract": "", "sections": []})
    assert result["sentences"] == []
    assert result["tokens"] == []
    assert result["detected_entities"] == []
    assert result["processing_metadata"]["input_text_length"] == 0


def test_pipeline_performance_edge_cases():
    pipeline = BiomedicalNLPPipeline()
    long_text = "cancer " * 200
    result = pipeline.process_document({"document_id": "edge", "abstract": long_text, "sections": []})
    assert result["sentences"]
    assert result["execution_metrics"]["stage_metrics"]["sentence_segmentation"]["processed_items"] >= 1


def test_relationship_extraction():
    pipeline = BiomedicalNLPPipeline()
    result = pipeline.process_document(make_doc())

    assert "relationships" in result
    assert result["relationships"]
    relationship = result["relationships"][0]
    assert relationship["predicate"] in {"treats", "associated_with", "interacts_with", "targets"}
    assert 0 <= relationship["confidence"] <= 1
    assert relationship["provenance"]["source_sentence"]


def test_summarizer_is_included_in_pipeline():
    pipeline = BiomedicalNLPPipeline()
    result = pipeline.process_document(make_doc())

    assert "summary" in result
    assert result["summary"]["document_id"] == "doc-001"
    assert result["summary"]["structured_summary"]
    assert "abstract_summary" in result["summary"]
    assert "key_findings" in result["summary"]
    assert "clinical_relevance" in result["summary"]
    assert "limitations" in result["summary"]


def test_embedding_generation_service():
    pipeline = BiomedicalNLPPipeline()
    nlp_result = pipeline.process_document(make_doc())
    service = EmbeddingService(batch_size=2)
    embeddings = service.generate_embeddings(nlp_result)

    assert embeddings["document_id"] == "doc-001"
    assert embeddings["embedding_batches"]
    assert embeddings["embedding_count"] >= 1
    assert embeddings["metadata"]["source"] == "EmbeddingService"
    assert embeddings["metadata"]["embedding_dimensions"] > 0
    assert embeddings["processing_metrics"]["batch_count"] >= 1


def test_search_integration_service_success_and_retries(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(self, url, **kwargs):
        calls.append((url, kwargs.get("json")))
        return FakeResponse({"status": "ok", "upserted": 1})

    monkeypatch.setattr("app.services.search_integration.httpx.Client.post", fake_post)

    service = SearchIntegrationService(base_url="http://search", timeout_seconds=1, max_retries=3)
    result = service.submit_embeddings("doc-001", [{"text": "hello", "embedding": [0.1, 0.2]}])

    assert result["status"] == "ok"
    assert result["upserted"] == 1
    assert calls[0][0] == "http://search/api/v1/search/index"


def test_search_integration_service_failure(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise RuntimeError("boom")

    def fake_post(self, url, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.services.search_integration.httpx.Client.post", fake_post)

    service = SearchIntegrationService(base_url="http://search", timeout_seconds=1, max_retries=2)
    with pytest.raises(RuntimeError):
        service.submit_embeddings("doc-001", [{"text": "hello", "embedding": [0.1, 0.2]}])


def test_legacy_process_document_wrapper():
    result = process_document(make_doc())
    assert result["document_id"] == "doc-001"
    assert "detected_entities" in result
