# Phase 4 — Temporal Intelligence

## Status

COMPLETE WITH DOCUMENTED LIMITATION

Phase 4 adds persisted knowledge-state historical retrieval to the Phase 3 canonical claims/evidence model. It reuses PostgreSQL canonical records and does not create a second temporal store.

## Timestamp semantics

The timestamps remain distinct; none is inferred from another:

- `source_records.published_at`: publication time supplied by the source, nullable.
- `source_records.source_updated_at`: source-reported update time, nullable.
- `source_records.observed_at`: source/event observation time, nullable.
- `source_records.ingested_at`: database-recorded time the source record entered AI-RxOS; defaulted by PostgreSQL at insert.
- `observations.valid_from` / `valid_to`: domain validity/effective interval, nullable.
- `observations.published_at`, `observed_at`, and `source_updated_at`: source timestamp copies for observation retrieval; they are not availability timestamps.
- `observations.ingested_at`: when the observation became available in the canonical store.
- `observations.manually_verified_at`: reviewer verification time, populated only for verified observations.
- `claims.created_at` and `evidence_links.created_at`: database transaction times used as their availability times. Claims/evidence do not have separate ingestion columns.
- `claims.valid_from` / `valid_to` and `evidence_links.valid_from` / `valid_to`: their respective domain validity intervals.

Unknown source, event, validity, and verification dates remain `NULL`. The model does not fabricate dates, set publication from ingestion, or use publication as ingestion. `valid_from` represents effective/domain time in this schema; there is no separate `effective_at` field. Date-only source values are not supported by these timestamp inputs unless the source owner supplies a timezone-aware instant.

## As-of semantics

`as_of=T` is a **knowledge-state** query: return claims and evidence AI-RxOS had recorded by T and whose stored validity windows include T. It is not a world-state query that retroactively includes material ingested later. Source publication/event times remain visible in lineage but do not decide whether the platform knew the record.

The validity interval is **closed/inclusive** at both supplied endpoints:

- `valid_from IS NULL OR valid_from <= T`
- `valid_to IS NULL OR valid_to >= T`

Thus an item is valid at exactly `valid_from` and exactly `valid_to`. A null endpoint is unbounded; both null means no declared validity restriction. Availability is also inclusive (`ingested_at <= T` / `created_at <= T`). If `as_of` is omitted, PostgreSQL `transaction_timestamp()` supplies the current cutoff and the same availability/validity rules apply.

The repository applies filtering in SQL before returning rows. Claim visibility and RLS/organization predicates are retained alongside temporal predicates. Lineage returns only qualifying evidence and nests the associated observation and source-record metadata, so excluded future evidence is not attached to a historical result.

## Late arrivals, updates, and contradictions

A record published in 2019 but ingested in 2021 is absent from a 2020 knowledge-state query and appears at/after its 2021 ingestion time if its valid-time window includes that cutoff. A later correction or contradiction is stored as additional evidence with its own provenance and validity window. Earlier evidence is not overwritten or deleted; no Phase 4 winner score is computed.

The focused PostgreSQL regression uses persisted fixed timestamps to verify an early supporting record, a late-arriving 2019 publication, a later contradiction, a correction, and unbounded/unknown dates over multiple cutoffs. It verifies closed start/end boundaries, pre-validity exclusion, availability boundary behavior, timezone-equivalent instants, evidence retention, and claim-to-evidence-to-observation-to-source lineage.

## API and migration

- `GET /api/v1/canonical/entities/{entity_id}/claims?as_of=<RFC3339>` filters in the repository query.
- `GET /api/v1/canonical/claims/{claim_id}/lineage?as_of=<RFC3339>` applies the same cutoff to claim, linked observation/source availability, evidence, and lineage.
- Timestamps must include a timezone; malformed or naive query timestamps are rejected by FastAPI/Pydantic validation. PostgreSQL stores and compares `TIMESTAMPTZ` instants.
- Additive migration `011_temporal_as_of_indexes.sql` adds indexes for entity/claim availability scans. Existing Phase 2/3 migrations were not edited.

## Verification

Against the local live PostgreSQL/Neo4j/Search stack:

- `python -m pytest -q services/kg/tests/test_phase_3_and_4.py` → `5 passed`.
- `python -m pytest -q services/kg/tests` with all live service variables → `88 passed`, no skips.
- B10 end-to-end plus canonical projection tests → `2 passed`.
- `python -m pytest -q` in `services/literature` → `109 passed`.
- `go test ./...` in `services/search` → passed.
- KG migration validation tests in the full suite exercise clean migration, repeat/upgrade stability, checksum drift, and transactional failure behavior.

## Limitations

This historical API covers canonical claims and their evidence lineage. It does not provide historical snapshots for legacy Neo4j graph routes, Search results, or every canonical list endpoint. Claims/evidence use `created_at` as their recorded availability time rather than separate ingestion columns. The system does not version reviewer verification state as a complete bitemporal history, and source owners must provide explicit timezone-aware timestamps; date-only interpretation is not guessed. These limits do not weaken the implemented knowledge-state guarantee for the claim/evidence API.
