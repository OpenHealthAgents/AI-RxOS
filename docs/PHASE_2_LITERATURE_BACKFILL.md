# Phase 2 Literature Backfill

## Scope

B02 replays the existing `literature_papers` table into the KG-owned canonical PostgreSQL store. It does not acquire new PubMed or PMC data and does not create a second identity system.

## Flow

`app.services.backfill` reads durable literature rows, preserves available source identifiers and metadata, normalizes DOI forms, and calls `CanonicalRepository.reconcile_legacy_record` for every record. B01 owns exact, possible, ambiguous, unresolved, and explicit `NEW_ENTITY` decisions.

Apply mode persists canonical publications, source identifiers, factual observations, source linkage, provenance, and only relationships that already contain canonical endpoint IDs. Missing or name-only extracted relationships are not inferred.

## Invocation

From `services/kg`:

```powershell
$env:DATABASE_URL = "postgresql://..."
$env:PYTHONPATH = "."
python -m app.commands.literature_backfill --dry-run
python -m app.commands.literature_backfill --apply --create-if-unresolved
```

Tenant runs require both `LITERATURE_BACKFILL_ORGANIZATION_ID` and `LITERATURE_BACKFILL_USER_ID`. The checkpoint defaults to `data/literature-backfill.json` and can be overridden with `--checkpoint`.

## Guarantees

- Dry-run performs source reading and B01 reconciliation without canonical writes or checkpoints.
- Apply is restart-safe through a durable checkpoint and source-scoped uniqueness.
- Repeated apply without a checkpoint reuses B01 identifiers and idempotent identifier/observation/relationship persistence.
- Malformed records are recorded as failures and do not stop later records.
- Tenant-scoped reads include public rows and the active tenant only. Unscoped runs include public rows only.
- Source-owned values are observations; model-generated guesses are not migrated.
- Existing literature storage is extended additively with abstract, authors, PMID, PMCID, journal, metadata, extraction payloads, and tenant ownership columns.

## Validation

Focused tests are in `services/kg/tests/test_backfill.py`. Migration and canonical regression tests run with the KG suite. Live validation used the repository's Compose PostgreSQL service and proved dry-run non-mutation, apply creation, exact-match replay, checkpoint skipping, failure isolation, and tenant A/B isolation.

The current historical schema contains only a subset of the richer connector payload, so unavailable abstract/authors/PMID/PMCID values remain absent rather than invented. Existing pipeline extraction payloads are migrated only when present in the durable table.
