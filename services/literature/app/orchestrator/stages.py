from __future__ import annotations

import logging
from typing import Any

from app.integrations.kg_client import KGClient
from app.integrations.wiki_client import LLMWikiClient
from app.knowledge.models import (
    TenantContext,
    deterministic_entity_id,
    normalize_entity_label,
)
from app.nlp.embedding_service import EmbeddingService
from app.nlp.pipeline import LiteratureNLP
from app.observability.metrics import metrics
from app.services.chunking import build_chunks
from app.services.search_integration import SearchIntegrationService

logger = logging.getLogger(__name__)


def _tenant_from_payload(payload: dict[str, Any]) -> TenantContext:
    return TenantContext.from_claims(payload.get("tenant"))


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


class ChunkingStage(PipelineStage):
    """Splits each item's normalized text into provenance-carrying chunks.

    Runs after entity/relationship extraction (so entity_ids can be
    attached) and before KGUpdateStage/WikiUpdateStage/SearchHandoffStage,
    which all consume item["chunks"].
    """

    name = "ChunkingStage"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        tenant = _tenant_from_payload(payload)
        for item in payload.get("items", []):
            document = item.get("document", {})
            entities = item.get("structured_entities", [])
            entity_ids: list[str] = []
            entity_types: list[str] = []
            for entity in entities:
                category = entity.get("type") or entity.get("category") or ""
                label = normalize_entity_label(category)
                if not label or not entity.get("text"):
                    continue
                entity_ids.append(deterministic_entity_id(category, entity["text"]))
                entity_types.append(label)

            item["chunks"] = build_chunks(
                document=document,
                text=item.get("normalized_text") or document.get("content", ""),
                source_type=document.get("source") or payload.get("source", "unknown"),
                entity_ids=entity_ids,
                entity_types=entity_types,
                tenant=tenant,
            )
        return payload


class KGUpdateStage(PipelineStage):
    name = "KGUpdateStage"

    def __init__(self, kg_client: KGClient):
        self.kg_client = kg_client

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        kg_results: list[dict[str, Any]] = []
        for item in payload.get("items", []):
            result = self.kg_client.update_knowledge_graph(
                item.get("structured_entities", []), item.get("relationships", [])
            )
            # Shares deterministic entity ids with the wiki chunks built in
            # ChunkingStage, so WikiUpdateStage can link back to KG nodes.
            item["kg_entity_id_map"] = result.get("entity_id_map", {})
            kg_results.append(result)
        return {**payload, "kg_updates": kg_results}


class WikiUpdateStage(PipelineStage):
    name = "WikiUpdateStage"

    def __init__(self, wiki_client: LLMWikiClient):
        self.wiki_client = wiki_client

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        tenant = _tenant_from_payload(payload).as_dict()
        wiki_results: list[dict[str, Any]] = []
        for item in payload.get("items", []):
            wiki_results.append(
                self.wiki_client.update_wiki(
                    item.get("document", {}),
                    item.get("structured_entities", []),
                    item.get("structured_summary", {}),
                    relationships=item.get("relationships", []),
                    evidence=item.get("evidence", []),
                    tenant=tenant,
                    chunks=item.get("chunks", []),
                )
            )
        return {**payload, "wiki_updates": wiki_results, "status": "completed"}


class SearchHandoffStage(PipelineStage):
    """Feeds indexed chunks + embeddings to the search service.

    This is the previously-missing link between the literature pipeline
    (Prompt 6) and search's semantic retrieval (Prompt 7): without it,
    LLMWikiProvider's local QMD index never receives any content. Failures
    are recorded per item rather than raised, matching the degrade-gracefully
    behavior of KGUpdateStage/WikiUpdateStage's underlying clients — a
    search outage should not fail literature ingestion.
    """

    name = "SearchHandoffStage"

    def __init__(
        self,
        search_client: SearchIntegrationService,
        embedding_service: EmbeddingService,
    ):
        self.search_client = search_client
        self.embedding_service = embedding_service

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        tenant = _tenant_from_payload(payload).as_dict()
        handoff_results: list[dict[str, Any]] = []
        for item in payload.get("items", []):
            chunks = item.get("chunks", [])
            if not chunks:
                continue
            document_id = str(
                chunks[0]["metadata"].get("document_id")
                or item.get("document", {}).get("source_id")
                or ""
            )
            if not document_id:
                continue
            documents = [
                {
                    "id": chunk["chunk_id"],
                    "document_id": document_id,
                    "title": chunk["metadata"].get("title", ""),
                    "content": chunk["text"],
                    "source": chunk["metadata"].get("source_type", "literature_service"),
                    "embedding": self.embedding_service.embed_text(chunk["text"]),
                }
                for chunk in chunks
            ]
            try:
                result = self.search_client.submit_embeddings(
                    document_id, documents, tenant=tenant
                )
            except RuntimeError as exc:
                metrics.increment("literature.search_handoff.failure")
                result = {
                    "document_id": document_id,
                    "status": "failed",
                    "error": str(exc),
                }
            handoff_results.append(result)
        return {**payload, "search_handoffs": handoff_results}
