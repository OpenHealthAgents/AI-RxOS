ALTER TABLE canonical.entities
    ADD COLUMN IF NOT EXISTS created_source_record_id UUID
    REFERENCES canonical.source_records(id) ON DELETE RESTRICT;
