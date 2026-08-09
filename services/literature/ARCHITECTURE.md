# Literature Service Architecture

## Scope
This service implements the Prompt 6 Literature Intelligence pipeline for AI-RxOS without replacing the existing stage-based orchestration model.

## Runtime Flow
1. `ConnectorFactory` selects a source-specific connector.
2. The connector performs source identification, fetch, parsing, and normalization into the common literature document model.
3. `LiteratureService` sends normalized documents through `PipelineRunner`.
4. `LiteratureNLP` performs parser normalization, heuristic NER/entity extraction, summarization fallback, relationship extraction, duplicate detection, and evidence ranking.
5. Integration stages call:
   - `KGClient` for knowledge graph update operations
   - `LLMWikiClient` for OKF wiki updates
6. `JobStore` persists ingestion job state to `data/ingestion_jobs.json`.

## Main Components
- `app/connectors/`
  Source-specific ingestion connectors for 11 required sources.
- `app/parsing/text_parser.py`
  Safe text cleanup and normalized document shaping.
- `app/nlp/`
  Replaceable entity extraction, summarization, relationships, deduplication, and ranking stages.
- `app/orchestrator/pipeline.py`
  Retry-aware stage runner with explicit job-state transitions.
- `app/integrations/`
  Integration boundaries for KG and LLM Wiki updates.
- `app/database/models.py`
  Pydantic job-state model and lightweight persistence store.

## Important Constraints
- No Airflow was introduced.
- No fake production records are generated when a source is unavailable.
- Conference and publisher sources expose documented limitations where direct structured access is constrained.
- NER is currently rule-based, not ML-based.

