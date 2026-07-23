-- 1. Audit log integrity columns
ALTER TABLE audit_log
  ADD COLUMN IF NOT EXISTS prev_hash TEXT,
  ADD COLUMN IF NOT EXISTS current_hash TEXT,
  ADD COLUMN IF NOT EXISTS signature TEXT;

-- 2. Audit log index improvements for verification and lookup
CREATE INDEX IF NOT EXISTS idx_audit_log_prev_hash ON audit_log(prev_hash);
CREATE INDEX IF NOT EXISTS idx_audit_log_current_hash ON audit_log(current_hash);

-- 3. Trigger functions for chained hashing and HMAC signing
CREATE OR REPLACE FUNCTION audit_log_hash_input(audit_row audit_log) RETURNS text AS $$
BEGIN
  RETURN CONCAT(
    COALESCE(audit_row.id::text, ''), '|',
    COALESCE(audit_row.user_id::text, ''), '|',
    COALESCE(audit_row.organization_id::text, ''), '|',
    COALESCE(audit_row.workspace_id::text, ''), '|',
    COALESCE(audit_row.project_id::text, ''), '|',
    COALESCE(audit_row.action, ''), '|',
    COALESCE(audit_row.resource_type, ''), '|',
    COALESCE(audit_row.resource_id::text, ''), '|',
    COALESCE(audit_row.ip_address, ''), '|',
    COALESCE(audit_row.user_agent, ''), '|',
    COALESCE(audit_row.metadata::text, ''), '|',
    COALESCE(audit_row.created_at::text, '')
  );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION audit_log_compute_hash(input_text text) RETURNS text AS $$
BEGIN
  RETURN encode(digest(input_text, 'sha256'), 'hex');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION audit_log_compute_signature(input_hash text) RETURNS text AS $$
DECLARE
  secret text := current_setting('audit.log_hmac_secret', true);
BEGIN
  IF secret IS NULL THEN
    RAISE EXCEPTION 'Audit log HMAC secret is not configured in the current session';
  END IF;
  RETURN encode(hmac(input_hash, secret, 'sha256'), 'hex');
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION audit_log_before_insert() RETURNS trigger AS $$
DECLARE
  raw_text text;
  new_hash text;
BEGIN
  raw_text := audit_log_hash_input(NEW);
  new_hash := audit_log_compute_hash(raw_text);
  NEW.prev_hash := (
    SELECT current_hash FROM audit_log
    ORDER BY created_at DESC, id DESC
    LIMIT 1
  );
  NEW.current_hash := new_hash;
  NEW.signature := audit_log_compute_signature(new_hash);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_before_insert ON audit_log;
CREATE TRIGGER trg_audit_log_before_insert
BEFORE INSERT ON audit_log
FOR EACH ROW EXECUTE FUNCTION audit_log_before_insert();

-- 4. Preserve immutability for UPDATE and DELETE operations
CREATE OR REPLACE FUNCTION audit_log_protect_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Audit log entries are immutable and cannot be updated or deleted';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_protect_audit_log ON audit_log;
CREATE TRIGGER trg_protect_audit_log
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION audit_log_protect_mutation();
