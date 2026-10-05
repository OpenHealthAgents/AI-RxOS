from pathlib import Path
import re


MIGRATIONS = Path(__file__).parents[1] / "migrations"


def _sql() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")))


def test_migrations_are_ordered_and_forward_only():
    names = [path.name for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))]
    numbers = [int(name[:3]) for name in names]
    assert numbers == list(range(1, len(numbers) + 1))
    assert all(
        any(marker in path.read_text(encoding="utf-8") for marker in (
            "CREATE TABLE IF NOT EXISTS", "ALTER TABLE", "DROP INDEX IF EXISTS",
            "CREATE INDEX IF NOT EXISTS",
        ))
        for path in MIGRATIONS.glob("*.sql")
    )


def test_canonical_schema_contains_phase_two_integrity_controls():
    sql = _sql().lower()
    for table in ("source_records", "entities", "identifiers", "aliases", "relationships", "observations", "projection_outbox", "reconciliation_results"):
        assert f"canonical.{table}" in sql
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert "foreign key" in sql or "references canonical." in sql
    assert "unique index" in sql
    assert "reconciliation_results_scoped_unique" in sql
    assert "organization_id" in sql


def test_migration_filenames_have_unique_numeric_order():
    names = [path.name for path in MIGRATIONS.glob("*.sql")]
    assert len(names) == len(set(names))
    assert all(re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", name) for name in names)