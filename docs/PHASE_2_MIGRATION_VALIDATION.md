# Phase 2 Migration Validation (B04)

## Scope

B04 validates the existing KG-owned canonical PostgreSQL migration runner and migrations. It does not introduce another migration framework and does not alter B01, B02, or B03 backfill behavior.

## Migration Inventory

1. `001_canonical_data_model.sql` — additive canonical schema, foreign keys, indexes, RLS, append-only observation trigger, and projection outbox.
2. `002_decouple_auth_ownership.sql` — forward-only ownership decoupling; removes dependencies on Auth tables.
3. `003_allow_ambiguous_names.sql` — forward-only compatibility change; removes the normalized-name uniqueness index.
4. `004_record_verification_actor.sql` — additive reviewer fields and verification constraints.
5. `005_entity_source_provenance.sql` — additive entity source-record reference.
6. `006_reconciliation_results.sql` — additive B01 reconciliation result table and scoped uniqueness.
7. `007_migration_checksums.sql` — additive migration checksum column/index.
8. `008_reconciliation_tenant_policy.sql` — additive RLS and tenant policy for reconciliation results.

The repository is intentionally forward-only. No down-migration directory or rollback API exists. Migrations 002 and 003 are intentionally irreversible compatibility changes; rollback is not pretended or simulated. Transactional failure/retry behavior is tested instead.

## Validation Matrix

Disposable PostgreSQL tests cover clean migration, repeated migration three times, migration ordering, checksum completeness, existing canonical data, B02/B03 source namespaces, checksum drift detection, transactional failure recovery, foreign keys, identifier uniqueness, RLS/policy presence, and append-only observations.

The live Compose PostgreSQL database was upgraded in place. Migrations 007 and 008 were applied and a repeat invocation made no changes. Live migration state contains all eight IDs with checksums and the reconciliation RLS policy.

## Checksum Safety

`CanonicalStore.apply_migrations` records SHA-256 checksums and detects edits to already-applied migrations. Existing rows without checksums are baselined once during the additive checksum upgrade. A mismatch raises before later migration work proceeds.

## Commands

```powershell
cd C:\Users\Lenovo\Downloads\AI-RxOS\services\kg
$env:PYTHONPATH = "."
$env:KG_TEST_DATABASE_URL = "postgresql://..."
pytest tests/test_migration_validation.py -q
pytest tests -q
python -m compileall -q app

Push-Location ..\..
git diff --check
Pop-Location
```

## Results

- Focused B04 suite: 6 passed.
- Full KG suite after B04 changes: validated separately with the repository command.
- Live PostgreSQL migration upgrade: migrations 007 and 008 applied successfully, repeat invocation stable.
- Live canonical counts after upgrade: 21 entities, 47 observations, 11 relationships.

Known intentional limitation: rollback/down migrations are not supported because the canonical schema contains append-only observations and forward-only compatibility changes. Validation uses disposable databases and transactional failure recovery instead of destructive rollback against real canonical data.
