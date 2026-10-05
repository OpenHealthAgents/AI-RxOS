# Phase 3 — Evidence Architecture

## Status

COMPLETE WITH DOCUMENTED LIMITATION

Phase 3 is implemented as an additive evidence layer on top of the existing Phase 2 canonical architecture. It keeps PostgreSQL as the authoritative store, preserves source records and observations as the source-backed truth, and adds durable claim/evidence lineage for explainability and contradiction tracking without creating a second scientific source-of-truth.

## Scope and architecture

The Phase 3 lineage is:

Source
-> Source Record
-> Observation
-> Claim
-> Evidence Link
-> Canonical Entity / Relationship

The design intentionally separates:

- observed facts from extracted or normalized observations;
- derived interpretations from direct source assertions;
- model output or prediction from source-backed fact;
- supporting and contradicting evidence from a single enforced conclusion.

This remains compatible with the Phase 2 canonical model. Evidence and claims attach to the existing source records, entities, and observations instead of replacing them.

## Data model

The additive canonical tables are:

- `canonical.claims`
  - id, entity_id, claim_type, statement, visibility, organization_id
  - confidence, source_record_id, observation_id
  - valid_from / valid_to, created_at
  - claim_type values include `source_fact`, `derived_claim`, `inference`, and `prediction`

- `canonical.evidence_links`
  - id, claim_id, observation_id or source_record_id
  - relation_type in `supporting`, `contradicting`, `context`, `derived`
  - metadata, visibility, organization_id, valid_from / valid_to

These rows are enforced by PostgreSQL CHECK constraints and repository-level tenant scope validation.

## Provenance and lineage

The implementation preserves retrieval provenance by requiring that:

- every claim is linked to a source record;
- every evidence link anchors to either an observation or a source record;
- every observation is itself linked to a source record;
- entity-level claim retrieval can resolve lineage without an LLM reconstructing the origin.

This allows tracing:

Evidence -> Claim -> Observation -> Source Record -> Source

## Observed vs inferred vs predicted

The model reuses the existing `ClaimType` enum and `ObservationKind` semantics:

- `source_fact`: direct observation or recorded source fact
- `derived_claim`: an interpretation built from source-backed evidence
- `inference`: explicit derived reasoning result
- `prediction`: model-produced or predictive output

The implementation keeps these states distinct rather than collapsing them into a single fact type, and it preserves provenance metadata on each claim.

## Supporting and contradicting evidence

The evidence model supports supporting and contradicting relationships explicitly. Both remain queryable and are preserved as separate rows; one does not overwrite or delete the other.

This is the required Phase 3 behavior for explainable evidence architecture: contradictory evidence is retained as contradiction, not suppressed as a false certainty.

## Tenant isolation and public visibility

The evidence and claim tables follow the existing canonical tenant model:

- tenant rows are scoped to `organization_id`
- global rows remain public if visibility is `global`
- private evidence is rejected for cross-tenant access
- unscoped reads fail closed
- repo-level checks enforce the same policy used by Phase 2 canonical records

The live KG suite validates this against the real PostgreSQL runtime with non-superuser tenant context.

## APIs

The KG canonical API includes the Phase 3 functions:

- `POST /api/v1/canonical/claims`
- `POST /api/v1/canonical/claims/{claim_id}/evidence`
- `GET /api/v1/canonical/entities/{entity_id}/claims`
- `GET /api/v1/canonical/claims/{claim_id}/lineage`

The repository methods implement the underlying create/link/list/get-lineage behavior and they keep the same canonical principal and tenant checks as the rest of the canonical service.

## Live validation

Executed successfully against the repo’s local PostgreSQL-backed environment:

- `python -m pytest -q services/kg/tests/test_phase_3_and_4.py` → `3 passed`
- `python -m pytest -q services/kg/tests` → `84 passed, 2 skipped`
- `cd services/literature; python -m pytest -q` → `109 passed`
- `cd services/search; go test ./...` → passed

The live Search service was also verified reachable at `http://localhost:8084/healthz` before the projection tests were rerun.

## Known limitations

This Phase 3 implementation intentionally does not create a full domain intelligence engine, recommendation engine, or decision scoring layer. It is only the provenance, claim, and evidence architecture needed to explain what AI-RxOS believes and why.

It also does not claim broad regulatory or clinical readiness; it remains a repository-scoped evidence foundation within the mature canonical architecture.
