-- 1. MFA table to support TOTP, backup codes, and recovery codes
CREATE TABLE IF NOT EXISTS mfa (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  totp_secret TEXT,
  backup_codes JSONB DEFAULT '[]'::jsonb,
  recovery_codes JSONB DEFAULT '[]'::jsonb,
  enabled BOOLEAN DEFAULT FALSE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mfa_user_id ON mfa(user_id);

-- Trigger to keep updated_at in sync
CREATE OR REPLACE FUNCTION mfa_updated_at_trigger() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_mfa_updated_at ON mfa;
CREATE TRIGGER trg_mfa_updated_at
BEFORE UPDATE ON mfa
FOR EACH ROW EXECUTE FUNCTION mfa_updated_at_trigger();
