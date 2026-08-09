from __future__ import annotations

import logging
from typing import Any

from app.connectors.factory import ConnectorFactory
from app.database.models import IngestionJobState, job_store
from app.integrations.kg_client import KGClient
from app.integrations.wiki_client import LLMWikiClient
from app.nlp.pipeline import LiteratureNLP
from app.observability.metrics import metrics
from app.orchestrator.pipeline import PipelineRunner
from app.orchestrator.stages import (
    DeduplicationStage,
    EvidenceRankingStage,
    KGUpdateStage,
    NERStage,
    ParsingStage,
    RelationshipExtractionStage,
    SummarizationStage,
    WikiUpdateStage,
)

logger = logging.getLogger(__name__)


class LiteratureService:
    """Service layer coordinating connectors, NLP pipeline, KG & LLM Wiki updates, and state persistence."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.nlp = LiteratureNLP(self.config)
        self.kg_client = KGClient(self.config)
        self.wiki_client = LLMWikiClient(self.config)

        self.pipeline = PipelineRunner(
            stages=[
                ParsingStage(self.nlp),
                NERStage(self.nlp),
                RelationshipExtractionStage(self.nlp),
                SummarizationStage(self.nlp),
                EvidenceRankingStage(self.nlp),
                DeduplicationStage(self.nlp),
                KGUpdateStage(self.kg_client),
                WikiUpdateStage(self.wiki_client),
            ],
            retries=2,
            delay_seconds=0.05,
        )


    def ingest(self, source: str, query: str, job_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        connector_config = {**self.config, **kwargs}
        connector = ConnectorFactory.create(source, connector_config)
        source_status = connector.connect()
        results = connector.fetch(query, **kwargs)
        metrics.increment(f"literature.{source}.ingest")
        if not results:
            metrics.increment(f"literature.{source}.no_results")

        initial_payload = {
            "source": source,
            "query": query,
            "items": results,
            "limitation": connector.get_limitation(),
            "source_status": source_status,
        }

        if job_id:
            job = job_store.get(job_id) or IngestionJobState(id=job_id, source=source, query=query)
            return self.pipeline.run_with_job(job, initial_payload)

        return self.pipeline.run(initial_payload)

    def analyze_text(self, text: str) -> dict[str, Any]:
        result = self.nlp.run(text)
        metrics.increment("literature.nlp.analyze")
        return result
