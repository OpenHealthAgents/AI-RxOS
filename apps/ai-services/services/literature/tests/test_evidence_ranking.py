import pytest

from app.services.evidence_ranking import EvidenceRankingService


def make_document():
    return {
        "document_id": "doc-001",
        "title": "Cancer Study",
        "abstract": "TP53 mutations are linked to cancer. Aspirin may help.",
    }


def test_ranking_correctness_and_confidence_aggregation():
    service = EvidenceRankingService()
    document = make_document()
    nlp_result = {
        "document_id": "doc-001",
        "sentences": ["TP53 mutations are linked to cancer."],
        "entities": [{"text": "TP53", "confidence_score": 0.92, "ontology_source": "HGNC"}],
        "relationships": [{
            "predicate": "treats",
            "confidence": 0.8,
            "provenance": {"source_sentence": "Aspirin may help."},
            "source": "TP53",
            "target": "cancer",
        }],
    }

    result = service.rank_evidence(document, nlp_result)

    assert result["document_id"] == "doc-001"
    assert len(result["evidence_items"]) == 2
    assert result["evidence_items"][0]["ranking_score"] >= result["evidence_items"][1]["ranking_score"]
    assert result["evidence_items"][0]["overall_confidence"] >= 0
    assert result["ranking_metrics"]["deduplicated_items"] == 2


def test_duplicate_evidence_handling():
    service = EvidenceRankingService()
    document = make_document()
    nlp_result = {
        "entities": [
            {"text": "TP53", "confidence_score": 0.9},
            {"text": "TP53", "confidence_score": 0.89},
        ],
        "relationships": [],
    }

    result = service.rank_evidence(document, nlp_result)

    assert len(result["evidence_items"]) == 1
    assert result["ranking_metrics"]["deduplicated_items"] == 1


def test_provenance_preservation():
    service = EvidenceRankingService()
    document = make_document()
    nlp_result = {
        "sentences": ["Sentence one."],
        "entities": [{"text": "EGFR", "confidence_score": 0.7, "ontology_source": "HGNC", "normalized_identifier": "HGNC:3236"}],
        "relationships": [],
    }

    result = service.rank_evidence(document, nlp_result)
    evidence = result["evidence_items"][0]

    assert evidence["provenance"]["source_sentence"] == "Sentence one."
    assert evidence["provenance"]["ontology_source"] == "HGNC"
    assert evidence["provenance"]["normalized_identifier"] == "HGNC:3236"


def test_malformed_input():
    service = EvidenceRankingService()
    with pytest.raises(ValueError):
        service.rank_evidence("not-a-dict", {})

    with pytest.raises(ValueError):
        service.rank_evidence({}, "not-a-dict")


def test_empty_input():
    service = EvidenceRankingService()
    result = service.rank_evidence(make_document(), {"entities": [], "relationships": []})

    assert result["evidence_items"] == []
    assert result["ranking_metrics"]["total_evidence_items"] == 0
