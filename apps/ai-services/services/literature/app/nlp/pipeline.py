from __future__ import annotations

import time
import unicodedata
from typing import Any

from app.nlp.confidence_scorer import ConfidenceScorer
from app.nlp.entity_extractor import EntityExtractor
from app.nlp.entity_normalizer import EntityNormalizer
from app.nlp.ontology_mapper import OntologyMapper
from app.nlp.relationship_extractor import RelationshipExtractor
from app.nlp.sentence_segmenter import SentenceSegmenter
from app.nlp.summarizer import SummarizerService
from app.nlp.tokenizer import BiomedicalTokenizer
from app.observability.metrics import (
    NLP_PROCESSING_DURATION_SECONDS,
    NLP_PROCESSING_ERRORS_TOTAL,
    NLP_PROCESSING_TOTAL,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BiomedicalNLPPipeline:
    """Modular biomedical NLP pipeline for Phase 5 document processing."""

    def __init__(self) -> None:
        self.segmenter = SentenceSegmenter()
        self.tokenizer = BiomedicalTokenizer()
        self.extractor = EntityExtractor()
        self.normalizer = EntityNormalizer()
        self.mapper = OntologyMapper()
        self.scorer = ConfidenceScorer()
        self.relationship_extractor = RelationshipExtractor()
        self.summarizer = SummarizerService()

    def process_document(self, document: dict[str, Any]) -> dict[str, Any]:
        start_time = time.perf_counter()
        warnings: list[str] = []
        try:
            if not isinstance(document, dict):
                raise TypeError("document must be a dictionary")

            document_id = document.get("document_id") or document.get("id") or "unknown"
            abstract = document.get("abstract") or ""
            sections = document.get("sections") or []
            if not isinstance(sections, list):
                sections = []
                warnings.append("sections was not a list; defaulted to empty")

            text_parts: list[str] = []
            if isinstance(abstract, str) and abstract.strip():
                text_parts.append(abstract)

            for section in sections:
                if isinstance(section, dict):
                    section_text = section.get("text") or ""
                    if isinstance(section_text, str) and section_text.strip():
                        text_parts.append(section_text)
                else:
                    warnings.append("section entry was malformed")

            combined_text = "\n\n".join(text_parts)
            combined_text = self._normalize_text(combined_text)
            input_text_length = len(combined_text)

            sentences = self.segmenter.segment(combined_text)
            tokens: list[list[str]] = [
                self.tokenizer.tokenize(sentence) for sentence in sentences
            ]

            detected_entities: list[dict[str, Any]] = []
            relationships: list[dict[str, Any]] = []
            for sentence in sentences:
                entities = self.extractor.extract(sentence)
                normalized_entities: list[dict[str, Any]] = []
                for entity in entities:
                    normalized = self.normalizer.normalize(entity)
                    mapping = self.mapper.map_entity(normalized)
                    normalized["normalized_identifier"] = mapping.get(
                        "normalized_identifier"
                    )
                    normalized["ontology_source"] = mapping.get("ontology_source")
                    normalized["confidence_score"] = self.scorer.score(normalized)
                    normalized_entities.append(normalized)
                    detected_entities.append(normalized)

                if normalized_entities:
                    relationships.extend(
                        self.relationship_extractor.extract(
                            normalized_entities, sentence
                        )
                    )

            summary = self.summarizer.summarize(document)
            elapsed = time.perf_counter() - start_time
            elapsed_ms = round(elapsed * 1000, 2)
            NLP_PROCESSING_TOTAL.inc()
            NLP_PROCESSING_DURATION_SECONDS.observe(elapsed)
            return {
                "document_id": document_id,
                "sentences": sentences,
                "tokens": tokens,
                "detected_entities": detected_entities,
                "entities": detected_entities,
                "relationships": relationships,
                "summary": summary,
                "processing_metadata": {
                    "input_text_length": input_text_length,
                    "warnings": warnings,
                    "source": "BiomedicalNLPPipeline",
                },
                "execution_metrics": {
                    "total_processing_time_ms": elapsed_ms,
                    "stage_metrics": {
                        "sentence_segmentation": {
                            "processed_items": len(sentences),
                            "duration_ms": round(
                                elapsed_ms / max(1, len(sentences) or 1), 2
                            ),
                        },
                        "tokenization": {
                            "processed_items": len(tokens),
                            "duration_ms": round(
                                elapsed_ms / max(1, len(tokens) or 1), 2
                            ),
                        },
                        "entity_extraction": {
                            "processed_items": len(detected_entities),
                            "duration_ms": round(
                                elapsed_ms / max(1, len(detected_entities) or 1), 2
                            ),
                        },
                    },
                },
            }
        except Exception:
            NLP_PROCESSING_ERRORS_TOTAL.inc()
            raise

    def _normalize_text(self, text: str) -> str:
        if not text or not isinstance(text, str):
            return ""
        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.replace("–", "-").replace("—", "-")
        return normalized.strip()


def process_document(document: dict[str, Any]) -> dict[str, Any]:
    pipeline = BiomedicalNLPPipeline()
    return pipeline.process_document(document)


class LiteratureNLP:
    """Coordinating NLP wrapper for text parsing, NER, summarization, relationships, ranking, and deduplication."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        from app.parsing.text_parser import TextParser
        from app.nlp.deduplication import DuplicateDetector
        from app.nlp.summarizer import DocumentSummarizer
        from app.nlp.relationships import RelationshipExtractor
        from app.nlp.evidence_ranking import EvidenceRanker

        self.parser = TextParser()
        self.duplicate_detector = DuplicateDetector()
        self.summarizer = DocumentSummarizer(self.config)
        self.relationship_extractor = RelationshipExtractor()
        self.evidence_ranker = EvidenceRanker()

        ner_provider = self.config.get("ner_provider", "rule_based")
        if ner_provider == "spacy":
            from app.nlp.ner import SpaCyEntityExtractor
            spacy_ner = SpaCyEntityExtractor()
            if spacy_ner.available:
                self.ner: Any = spacy_ner
            else:
                from app.nlp.ner import RuleBasedEntityExtractor
                self.ner = RuleBasedEntityExtractor()
        else:
            from app.nlp.ner import RuleBasedEntityExtractor
            self.ner = RuleBasedEntityExtractor()

    def parse_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        return self.parser.normalize_document(doc)

    def detect_duplicate(self, doc_a: dict[str, Any], doc_b: dict[str, Any]) -> dict[str, Any]:
        return self.duplicate_detector.detect_duplicate(doc_a, doc_b)

    def extract_relationships(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        return self.relationship_extractor.extract(doc, doc.get("entities"))

    def run(self, text: str) -> dict[str, Any]:
        doc = {
            "title": "Biomedical Text Analysis",
            "abstract": text,
            "content": text,
            "source": "nlp_run",
            "source_id": "nlp_run_1",
        }
        parsed_doc = self.parse_document(doc)
        entities = self.ner.extract_entities(text)
        parsed_doc["entities"] = entities

        relationships = self.extract_relationships(parsed_doc)
        summary = self.summarizer.summarize(parsed_doc)
        evidence = self.evidence_ranker.rank_document(parsed_doc)

        return {
            "entities": [e["text"] for e in entities],
            "summary": summary.get("concise_summary", ""),
            "evidence": [evidence],
            "relationships": relationships,
            "parsed": parsed_doc,
        }
