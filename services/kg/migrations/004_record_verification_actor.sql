ALTER TABLE canonical.aliases
    ADD COLUMN IF NOT EXISTS verified_by UUID;

ALTER TABLE canonical.aliases
    ADD CONSTRAINT aliases_verification_actor_check
    CHECK ((verification_state <> 'verified') OR (verified_by IS NOT NULL AND verified_at IS NOT NULL));
