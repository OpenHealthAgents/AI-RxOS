ALTER TABLE canonical.schema_migrations
    ADD COLUMN IF NOT EXISTS checksum TEXT;

CREATE INDEX IF NOT EXISTS schema_migrations_applied_at_idx
    ON canonical.schema_migrations (applied_at);
