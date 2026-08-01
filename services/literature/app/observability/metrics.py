from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

registry = CollectorRegistry()

REQUEST_COUNT = Counter(
    "literature_http_requests_total",
    "Total number of HTTP requests processed by the literature service",
    ["method", "endpoint", "status"],
    registry=registry,
)
REQUEST_IN_FLIGHT = Gauge(
    "literature_http_requests_in_flight",
    "Current number of in-flight HTTP requests",
    ["method", "endpoint"],
    registry=registry,
)
REQUEST_LATENCY_SECONDS = Histogram(
    "literature_http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    registry=registry,
)
REQUEST_ERRORS = Counter(
    "literature_http_request_errors_total",
    "Total number of HTTP request errors",
    ["method", "endpoint", "status"],
    registry=registry,
)

NLP_PROCESSING_TOTAL = Counter(
    "literature_nlp_pipeline_runs_total",
    "Total number of biomedical NLP pipeline executions",
    registry=registry,
)
NLP_PROCESSING_ERRORS_TOTAL = Counter(
    "literature_nlp_pipeline_errors_total",
    "Total errors during biomedical NLP pipeline executions",
    registry=registry,
)
NLP_PROCESSING_DURATION_SECONDS = Histogram(
    "literature_nlp_pipeline_duration_seconds",
    "Biomedical NLP pipeline execution time in seconds",
    registry=registry,
)
RELATIONSHIP_EXTRACTION_TOTAL = Counter(
    "literature_relationship_extraction_total",
    "Total relationship extraction operations",
    registry=registry,
)
RELATIONSHIP_EXTRACTION_ERRORS_TOTAL = Counter(
    "literature_relationship_extraction_errors_total",
    "Total relationship extraction errors",
    registry=registry,
)
RELATIONSHIP_EXTRACTION_DURATION_SECONDS = Histogram(
    "literature_relationship_extraction_duration_seconds",
    "Relationship extraction duration in seconds",
    registry=registry,
)
SUMMARIZER_TOTAL = Counter(
    "literature_summarizer_total",
    "Total summarization operations",
    registry=registry,
)
SUMMARIZER_ERRORS_TOTAL = Counter(
    "literature_summarizer_errors_total",
    "Total summarization errors",
    registry=registry,
)
SUMMARIZER_DURATION_SECONDS = Histogram(
    "literature_summarizer_duration_seconds",
    "Summarization duration in seconds",
    registry=registry,
)
EMBEDDING_GENERATION_TOTAL = Counter(
    "literature_embedding_generation_total",
    "Total embedding generation requests",
    registry=registry,
)
EMBEDDING_GENERATION_ERRORS_TOTAL = Counter(
    "literature_embedding_generation_errors_total",
    "Total errors during embedding generation",
    registry=registry,
)
EMBEDDING_GENERATION_DURATION_SECONDS = Histogram(
    "literature_embedding_generation_duration_seconds",
    "Embedding generation duration in seconds",
    registry=registry,
)
SEARCH_HANDOFF_TOTAL = Counter(
    "literature_search_handoff_total",
    "Total search handoff attempts",
    ["status"],
    registry=registry,
)
SEARCH_HANDOFF_RETRIES_TOTAL = Counter(
    "literature_search_handoff_retries_total",
    "Total search handoff retries",
    registry=registry,
)
SEARCH_HANDOFF_ERRORS_TOTAL = Counter(
    "literature_search_handoff_errors_total",
    "Total search handoff failures",
    registry=registry,
)
SEARCH_HANDOFF_DURATION_SECONDS = Histogram(
    "literature_search_handoff_duration_seconds",
    "Search handoff duration in seconds",
    registry=registry,
)
KG_HANDOFF_TOTAL = Counter(
    "literature_kg_handoff_total",
    "Total KG handoff attempts",
    ["status"],
    registry=registry,
)
KG_HANDOFF_RETRIES_TOTAL = Counter(
    "literature_kg_handoff_retries_total",
    "Total KG handoff retries",
    registry=registry,
)
KG_HANDOFF_ERRORS_TOTAL = Counter(
    "literature_kg_handoff_errors_total",
    "Total KG handoff failures",
    registry=registry,
)
KG_HANDOFF_DURATION_SECONDS = Histogram(
    "literature_kg_handoff_duration_seconds",
    "KG handoff duration in seconds",
    registry=registry,
)
EVIDENCE_RANKING_TOTAL = Counter(
    "literature_evidence_ranking_total",
    "Total evidence ranking operations",
    registry=registry,
)
EVIDENCE_RANKING_ERRORS_TOTAL = Counter(
    "literature_evidence_ranking_errors_total",
    "Total evidence ranking failures",
    registry=registry,
)
EVIDENCE_RANKING_DURATION_SECONDS = Histogram(
    "literature_evidence_ranking_duration_seconds",
    "Evidence ranking duration in seconds",
    registry=registry,
)
LLMWIKI_UPDATE_TOTAL = Counter(
    "literature_llmwiki_update_total",
    "Total LLM Wiki update attempts",
    ["status"],
    registry=registry,
)
LLMWIKI_UPDATE_RETRIES_TOTAL = Counter(
    "literature_llmwiki_update_retries_total",
    "Total LLM Wiki update retries",
    registry=registry,
)
LLMWIKI_UPDATE_ERRORS_TOTAL = Counter(
    "literature_llmwiki_update_errors_total",
    "Total LLM Wiki update failures",
    registry=registry,
)
LLMWIKI_UPDATE_DURATION_SECONDS = Histogram(
    "literature_llmwiki_update_duration_seconds",
    "LLM Wiki update duration in seconds",
    registry=registry,
)


def generate_prometheus_metrics() -> bytes:
    return generate_latest(registry)
