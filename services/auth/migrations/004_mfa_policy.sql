-- Add organization-level MFA policy flag
ALTER TABLE organization ADD COLUMN IF NOT EXISTS mfa_required BOOLEAN DEFAULT FALSE NOT NULL;

-- Optional index for quick lookup
CREATE INDEX IF NOT EXISTS idx_organization_mfa_required ON organization(mfa_required) WHERE mfa_required = true;
