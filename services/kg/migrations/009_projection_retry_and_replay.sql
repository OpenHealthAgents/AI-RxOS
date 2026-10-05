ALTER TABLE canonical.projection_outbox
    ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 10,
    ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS projection_outbox_dead_letter_idx
    ON canonical.projection_outbox (dead_lettered_at)
    WHERE dead_lettered_at IS NOT NULL;
