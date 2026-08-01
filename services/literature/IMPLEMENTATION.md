# Implementation Overview

The AI-RxOS Literature service is implemented as a FastAPI application that ingests literature content, executes biomedical NLP, and hands off structured outputs to search, knowledge graph, and LLM Wiki services.

## Architecture

The service is organized into distinct functional layers:

- `app/core/`
  - `config.py` loads runtime settings and environment defaults.
  - `security.py` enforces JWT bearer authentication for protected endpoints.
  - `lifespan.py` manages startup and shutdown behavior, including PostgreSQL initialization and orchestrator lifecycle.

- `app/connectors/`
  - Implements source connectors for PubMed, PMC, ClinicalTrials, bioRxiv, medRxiv, patents, and company websites.
  - `registry.py` maps source names to connector factories.
  - `http_client.py` centralizes HTTP client behavior for connector communication.

- `app/parsing/`
  - `parser.py` extracts canonical metadata from HTML, XML, and PDF inputs.
  - `duplicates.py` detects duplicate documents by fingerprint.
  - `metrics.py` tracks parser-specific metrics.

- `app/nlp/`
  - `pipeline.py` composes sentence segmentation, tokenization, entity extraction, normalization, ontology mapping, relationship extraction, summarization, and confidence scoring.
  - `sentence_segmenter.py`, `tokenizer.py`, `entity_extractor.py`, `entity_normalizer.py`, `ontology_mapper.py`, `relationship_extractor.py`, `summarizer.py`, and `confidence_scorer.py` implement the processing stages.

- `app/services/`
  - `search_integration.py` sends embedding payloads to the downstream Search service.
  - `kg_integration.py` publishes published nodes and relationships to the KG service.
  - `llmwiki_integration.py` updates the LLM Wiki service with structured summaries and entity data.
  - `evidence_ranking.py` ranks evidence items from parsed and extracted content.

- `app/orchestrator/`
  - `manager.py` maintains ingestion jobs, scheduling, retries, dead-letter handling, and background worker execution.

- `app/database/`
  - `postgres.py` initializes an asyncpg pool and ensures the schema for papers and ingestion jobs.

- `app/routers/`
  - Defines API endpoints for health, documents, NLP, ingestion, and papers.
  - Authenticated request handling is applied through `app/core/security.py`.

- `app/observability/`
  - `metrics.py` defines Prometheus counters, histograms, and metrics exposition.

## Request flow

1. A request enters through FastAPI in `app/main.py`.
2. Middleware assigns a request ID and trace ID, collects request metrics, and instruments latency and error counts.
3. Routes are handled by `app/routers/*`.
4. For ingestion, jobs are persisted in PostgreSQL and queued by the orchestrator.
5. For parsing, `app/parsing/parser.py` normalizes content and checks duplicates.
6. For NLP processing, `app/nlp/pipeline.py` performs all extraction and summarization.
7. External integrations may hand off results to downstream systems.
8. Metrics and health endpoints expose service status.

## Data model

Key Pydantic models are defined in `app/schemas.py` and `app/document_schemas.py`.

- `DocumentParseRequest` requires `format` and `content`.
- `DocumentParseResponse` returns parsed metadata, duplicate status, and metrics.
- `IngestionRequest` includes source, query, and optional schedule.
- `IngestionJob` describes persisted ingestion job state.
- `Paper` describes stored paper metadata.

## Orchestrator behavior

- Jobs are queued or scheduled via `app/orchestrator/manager.py`.
- `schedule` jobs use cron syntax and are rescheduled after completion.
- `retry` increments retry count and applies backoff.
- `cancel` marks jobs as cancelled and persists state.
- Failed jobs populate a dead letter queue and increment dead-letter metrics.

## Observability

- Request-level metrics measured in `app/main.py` track:
  - total requests
  - request errors
  - in-flight requests
  - request latency
- Pipeline and integration metrics are defined in `app/observability/metrics.py`.
- Prometheus metrics are exposed at `/metrics/prometheus`.

## Production considerations

- The lifespan handler ensures the database schema is created on startup.
- Health and readiness checks make the service safe to deploy behind orchestration systems.
- JWT authentication protects all production-facing endpoints.
- Real downstream integration relies on external Search, KG, and LLM Wiki services.
