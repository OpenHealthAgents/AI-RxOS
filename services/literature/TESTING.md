# Testing Guide

This service includes unit and integration tests under `tests/`.

## Test structure

Key test files:

- `test_health.py` — liveness and basic health endpoints
- `test_health_readiness.py` — readiness checks and dependency handling
- `test_document_parser.py` — document parsing and duplicate detection
- `test_nlp_pipeline.py` — NLP processing pipeline logic
- `test_connectors.py` — connector registry and source connector behavior
- `test_clinicaltrials_ingestion.py` — ClinicalTrials.gov API v2 normalization,
  token pagination, malformed-record isolation, bounded retries, and durable
  processor resume behavior
- `test_regulatory_ingestion.py` — deterministic openFDA normalization,
  pagination boundaries, timeout/transient retries, malformed submissions,
  durable completion and interrupted-job recovery
- `test_google_patents_connector.py` — deterministic Google Patents response
  parsing, source-date precision, page tokens, malformed records, and bounded
  rate-limit retries
- `test_patent_ingestion.py` — durable patent processor checkpoint/restart,
  record-level malformed handling, and canonical handoff idempotence
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
- PostgreSQL persistence tests use `LITERATURE_TEST_DATABASE_URL` for a
  restricted runtime role and `LITERATURE_TEST_MIGRATION_DATABASE_URL` for a
  schema-owner connection. If unset, they fall back to `KG_TEST_DATABASE_URL`
  and `KG_TEST_MIGRATION_DATABASE_URL`. The split lets the full suite also run
  database-admin tenant-security tests without granting extra privileges to
  the Literature runtime role.

## Recommended validation

- Run `python -m pytest -q` after any code changes.
- Ensure endpoints and route handlers are covered by tests.
- Verify that authentication failures and invalid payloads are handled correctly.
- Run `python -m pytest -q tests/test_clinicaltrials_ingestion.py` for
  deterministic ClinicalTrials adapter/recovery coverage.
- Run the ClinicalTrials case in `services/kg/tests/test_pubmed_ingestion.py`
  with `KG_TEST_DATABASE_URL` set to an isolated PostgreSQL test database for
  canonical NCT identity, evidence lineage, temporal revisions, and tenant
  checks. No test requires a live ClinicalTrials.gov request.
- Run `python -m pytest -q tests/test_regulatory_ingestion.py` for deterministic
  FDA adapter and recovery tests. PostgreSQL-backed canonical and Literature
  snapshot tests use the regulatory cases in `services/kg/tests/test_pubmed_ingestion.py`
  and `tests/test_pubmed_persistence.py` with the isolated database variables
  configured. No deterministic test requires live openFDA access.
- Run `python -m pytest -q tests/test_google_patents_connector.py tests/test_patent_ingestion.py`
  for deterministic patent adapter and restart behavior. PostgreSQL-backed
  current-row/snapshot idempotence and durable job checkpoint recovery are
  covered by `test_patent_source_snapshot_and_identity_are_idempotent` and
  `test_literature_job_checkpoints_survive_restart` in
  `tests/test_pubmed_persistence.py`. Canonical patent/family/licensing
  identity, evidence, as-of, and tenant tests are in
  `services/kg/tests/test_ip_ingestion.py`. No deterministic test depends on
  live Google Patents availability.

## Troubleshooting test failures

- Check that required dependencies from `requirements.txt` are installed.
- Confirm the selected Python interpreter is 3.12.
- If tests fail due to missing services, use mocks or set `environment` to `test`.
