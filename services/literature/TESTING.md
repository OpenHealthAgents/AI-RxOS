# Testing Guide

This service includes unit and integration tests under `tests/`.

## Test structure

Key test files:

- `test_health.py` — liveness and basic health endpoints
- `test_health_readiness.py` — readiness checks and dependency handling
- `test_document_parser.py` — document parsing and duplicate detection
- `test_nlp_pipeline.py` — NLP processing pipeline logic
- `test_connectors.py` — connector registry and source connector behavior
- `test_company_website_connector.py` — company website ingestion connector
- `test_http_client.py` — HTTP client error handling
- `test_orchestrator.py` — ingestion job lifecycle, scheduling, retry, and cancel flows
- `test_observability.py` — metrics registration and snapshot behavior
- `test_prometheus_metrics.py` — Prometheus exposition output
- `test_kg_integration.py` — KG service payload construction and publish semantics
- `test_llmwiki_integration.py` — LLM Wiki payload validation and retry behavior
- `test_evidence_ranking.py` — evidence ranking logic

## Running tests

From `services/literature/`:

```bash
python -m pytest -q
```

This command executes the full test suite and will fail the run if any tests fail.

## Test environment

- `conftest.py` provides shared fixtures and test configuration.
- The service uses `environment = "test"` in test mode to skip real PostgreSQL startup behavior in the lifespan handler.

## Recommended validation

- Run `python -m pytest -q` after any code changes.
- Ensure endpoints and route handlers are covered by tests.
- Verify that authentication failures and invalid payloads are handled correctly.

## Troubleshooting test failures

- Check that required dependencies from `requirements.txt` are installed.
- Confirm the selected Python interpreter is 3.12.
- If tests fail due to missing services, use mocks or set `environment` to `test`.
