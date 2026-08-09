from __future__ import annotations

import logging
from typing import Any

from app.integrations.kg_client import KGClient
from app.integrations.wiki_client import LLMWikiClient
from app.nlp.pipeline import LiteratureNLP
from app.observability.metrics import metrics

logger = logging.getLogger(__name__)


class PipelineStage:
    """Base pipeline stage for reusable, callable stage implementations."""

    name = "PipelineStage"

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("Starting stage %s", self.name)
        try:
            result = self.run(payload)
            logger.info("Completed stage %s", self.name)
            metrics.increment(f"pipeline.stage.{self.name}.completed")
            return result
        except Exception as exc:
            logger.error("Stage %s failed: %s", self.name, exc)
            metrics.increment(f"pipeline.stage.{self.name}.failed")
            raise

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("PipelineStage subclasses must implement run()")


class ParsingStage(PipelineStage):
    name = "ParsingStage"

    def __init__(self, nlp: LiteratureNLP):
        self.nlp = nlp

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items", [])
        processed_items: list[dict[str, Any]] = []

        for item in items:
            normalized = self.nlp.parse_document(item)
            parsed_structure = self.nlp.parser.parse(normalized.get("content", ""))
            processed_items.append(
                {
                    "document": normalized,
                    "parsed": parsed_structure,
                    "normalized_text": parsed_structure.get("text", ""),
                }
            )

        return {**payload, "processed_items": processed_items}


class NERStage(PipelineStage):
    name = "NERStage"

    def __init__(self, nlp: LiteratureNLP):
        self.nlp = nlp

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("processed_items", [])
        for item in items:
            text = item.get("normalized_text", "")
            entities = self.nlp.ner.extract_entities(text)
            item["entities"] = [entity["text"] for entity in entities]
            item["structured_entities"] = entities
        return payload


class RelationshipExtractionStage(PipelineStage):
    name = "RelationshipExtractionStage"

    def __init__(self, nlp: LiteratureNLP):
        self.nlp = nlp

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("processed_items", [])
        for item in items:
            item["relationships"] = self.nlp.extract_relationships(
                {**item.get("document", {}), "entities": item.get("structured_entities", [])}
            )
        return payload


class SummarizationStage(PipelineStage):
    name = "SummarizationStage"

    def __init__(self, nlp: LiteratureNLP):
        self.nlp = nlp

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("processed_items", [])
        for item in items:
            summary_struct = self.nlp.summarizer.summarize(item.get("document", {}))
            item["summary"] = summary_struct.get("concise_summary", "")
            item["structured_summary"] = summary_struct
        return payload


class EvidenceRankingStage(PipelineStage):
    name = "EvidenceRankingStage"

    def __init__(self, nlp: LiteratureNLP):
        self.nlp = nlp

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("processed_items", [])
        for item in items:
            ranking = self.nlp.evidence_ranker.rank_document(item.get("document", {}))
            item["evidence_ranking"] = ranking
            item["evidence"] = [
                {"entity": e["text"], "category": e.get("category", "unknown"), "score": ranking["score"]}
                for e in item.get("structured_entities", [])
            ]
            if not item["evidence"]:
                item["evidence"] = [{"entity": "literature_document", "score": ranking["score"]}]
        return payload


class DeduplicationStage(PipelineStage):
    name = "DeduplicationStage"

    def __init__(self, nlp: LiteratureNLP):
        self.nlp = nlp

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("processed_items", [])
        deduped: list[dict[str, Any]] = []
        duplicates_found: list[dict[str, Any]] = []

        for item in items:
            doc = item.get("document", {})
            is_duplicate = False
            for existing in deduped:
                existing_doc = existing.get("document", {})
                dup_result = self.nlp.detect_duplicate(doc, existing_doc)
                if dup_result.get("duplicate"):
                    is_duplicate = True
                    duplicates_found.append(
                        {
                            "item": doc,
                            "duplicate_of": existing_doc,
                            "reason": dup_result.get("reason"),
                        }
                    )
                    metrics.increment("literature.duplicate_detected")
                    break
            if not is_duplicate:
                deduped.append(item)

        return {**payload, "items": deduped, "duplicates": duplicates_found}


class KGUpdateStage(PipelineStage):
    name = "KGUpdateStage"

    def __init__(self, kg_client: KGClient):
        self.kg_client = kg_client

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        kg_results: list[dict[str, Any]] = []
        for item in payload.get("items", []):
            kg_results.append(
                self.kg_client.update_knowledge_graph(
                    item.get("structured_entities", []), item.get("relationships", [])
                )
            )
        return {**payload, "kg_updates": kg_results}


class WikiUpdateStage(PipelineStage):
    name = "WikiUpdateStage"

    def __init__(self, wiki_client: LLMWikiClient):
        self.wiki_client = wiki_client

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        wiki_results: list[dict[str, Any]] = []
        for item in payload.get("items", []):
            wiki_results.append(
                self.wiki_client.update_wiki(
                    item.get("document", {}),
                    item.get("structured_entities", []),
                    item.get("structured_summary", {}),
                )
            )
        return {**payload, "wiki_updates": wiki_results, "status": "completed"}
