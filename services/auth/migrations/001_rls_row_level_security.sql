-- 1. Enable Core Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Define App Tenant Context Helper Function
CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS uuid AS $$
  SELECT NULLIF(current_setting('app.organization_id', true), '')::uuid
$$ LANGUAGE sql STABLE;

-- 3. Core BetterAuth Tables
CREATE TABLE IF NOT EXISTS "user" (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  email_verified BOOLEAN DEFAULT FALSE NOT NULL,
  name TEXT NOT NULL,
  image TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_email ON "user"(email);

CREATE TABLE IF NOT EXISTS account (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  access_token TEXT,
  refresh_token TEXT,
  id_token TEXT,
  expires_at TIMESTAMP WITH TIME ZONE,
  password TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  UNIQUE(account_id, provider_id)
);

CREATE INDEX IF NOT EXISTS idx_account_user_id ON account(user_id);

CREATE TABLE IF NOT EXISTS passkey_device (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  name TEXT,
  last_used_at TIMESTAMP WITH TIME ZONE,
  revoked_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_passkey_account_id ON passkey_device(account_id);

CREATE TABLE IF NOT EXISTS session (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  token TEXT UNIQUE NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_user_id ON session(user_id);
CREATE INDEX IF NOT EXISTS idx_session_token ON session(token);

CREATE TABLE IF NOT EXISTS verification (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  identifier TEXT NOT NULL,
  value TEXT NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_verification_identifier ON verification(identifier);

CREATE TABLE IF NOT EXISTS organization (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  logo TEXT,
  plan TEXT DEFAULT 'free' NOT NULL,
  max_users INTEGER DEFAULT 5 NOT NULL,
  max_workspaces INTEGER DEFAULT 3 NOT NULL,
  settings JSONB DEFAULT '{}'::jsonb NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_organization_slug ON organization(slug);
CREATE INDEX IF NOT EXISTS idx_organization_deleted_at ON organization(deleted_at) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS member (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  UNIQUE(organization_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_member_org_id ON member(organization_id);
CREATE INDEX IF NOT EXISTS idx_member_user_id ON member(user_id);

CREATE TABLE IF NOT EXISTS invitation (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  status TEXT NOT NULL DEFAULT 'pending',
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  inviter_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invitation_org ON invitation(organization_id);

CREATE TABLE IF NOT EXISTS workspace (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  settings JSONB DEFAULT '{}'::jsonb NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_workspace_org_id ON workspace(organization_id);

CREATE TABLE IF NOT EXISTS workspace_member (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member',
  joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  UNIQUE(workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS project (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'active' NOT NULL,
  settings JSONB DEFAULT '{}'::jsonb NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_project_ws_id ON project(workspace_id);

CREATE TABLE IF NOT EXISTS project_member (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member',
  joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  UNIQUE(project_id, user_id)
);

CREATE TABLE IF NOT EXISTS api_key (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspace(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  key_hash TEXT UNIQUE NOT NULL,
  prefix TEXT NOT NULL,
  scopes TEXT[] DEFAULT '{}'::text[] NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE,
  last_used_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
  revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_api_key_org ON api_key(organization_id);

CREATE TABLE IF NOT EXISTS audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES "user"(id) ON DELETE SET NULL,
  organization_id UUID REFERENCES organization(id) ON DELETE SET NULL,
  workspace_id UUID REFERENCES workspace(id) ON DELETE SET NULL,
  project_id UUID REFERENCES project(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID,
  ip_address TEXT,
  user_agent TEXT,
  metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_org ON audit_log(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

ALTER TABLE "user" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user" FORCE ROW LEVEL SECURITY;

ALTER TABLE session ENABLE ROW LEVEL SECURITY;
ALTER TABLE session FORCE ROW LEVEL SECURITY;

ALTER TABLE passkey_device ENABLE ROW LEVEL SECURITY;
ALTER TABLE passkey_device FORCE ROW LEVEL SECURITY;

ALTER TABLE organization ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization FORCE ROW LEVEL SECURITY;

ALTER TABLE member ENABLE ROW LEVEL SECURITY;
ALTER TABLE member FORCE ROW LEVEL SECURITY;

ALTER TABLE invitation ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitation FORCE ROW LEVEL SECURITY;

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

ALTER TABLE workspace ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace FORCE ROW LEVEL SECURITY;

ALTER TABLE project ENABLE ROW LEVEL SECURITY;
ALTER TABLE project FORCE ROW LEVEL SECURITY;

ALTER TABLE api_key ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_key FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'workspace' AND policyname = 'workspace_isolation') THEN
    CREATE POLICY workspace_isolation ON workspace FOR ALL
      USING (app_current_tenant() IS NULL OR organization_id = app_current_tenant())
      WITH CHECK (app_current_tenant() IS NULL OR organization_id = app_current_tenant());
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'project' AND policyname = 'project_isolation') THEN
    CREATE POLICY project_isolation ON project FOR ALL
      USING (app_current_tenant() IS NULL OR EXISTS (
        SELECT 1 FROM workspace WHERE workspace.id = project.workspace_id AND workspace.organization_id = app_current_tenant()
      ))
      WITH CHECK (app_current_tenant() IS NULL OR EXISTS (
        SELECT 1 FROM workspace WHERE workspace.id = project.workspace_id AND workspace.organization_id = app_current_tenant()
      ));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'audit_log' AND policyname = 'audit_log_isolation') THEN
    CREATE POLICY audit_log_isolation ON audit_log FOR ALL
      USING (app_current_tenant() IS NULL OR organization_id = app_current_tenant())
      WITH CHECK (app_current_tenant() IS NULL OR organization_id = app_current_tenant());
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'user' AND policyname = 'user_isolation') THEN
    CREATE POLICY user_isolation ON "user" FOR SELECT
      USING (app_current_tenant() IS NULL OR EXISTS (
        SELECT 1 FROM member WHERE member.user_id = "user".id AND member.organization_id = app_current_tenant()
      ));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'account' AND policyname = 'account_isolation') THEN
    CREATE POLICY account_isolation ON account FOR SELECT
      USING (app_current_tenant() IS NULL OR EXISTS (
        SELECT 1 FROM member WHERE member.user_id = account.user_id AND member.organization_id = app_current_tenant()
      ));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'member' AND policyname = 'member_isolation') THEN
    CREATE POLICY member_isolation ON member FOR ALL
      USING (app_current_tenant() IS NULL OR organization_id = app_current_tenant())
      WITH CHECK (app_current_tenant() IS NULL OR organization_id = app_current_tenant());
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'invitation' AND policyname = 'invitation_isolation') THEN
    CREATE POLICY invitation_isolation ON invitation FOR ALL
      USING (app_current_tenant() IS NULL OR organization_id = app_current_tenant())
      WITH CHECK (app_current_tenant() IS NULL OR organization_id = app_current_tenant());
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'passkey_device' AND policyname = 'passkey_device_isolation') THEN
    CREATE POLICY passkey_device_isolation ON passkey_device FOR ALL
      USING (app_current_tenant() IS NULL OR EXISTS (
        SELECT 1 FROM account a JOIN member m ON m.user_id = a.user_id
        WHERE a.id = passkey_device.account_id AND m.organization_id = app_current_tenant()
      ))
      WITH CHECK (app_current_tenant() IS NULL OR EXISTS (
        SELECT 1 FROM account a JOIN member m ON m.user_id = a.user_id
        WHERE a.id = passkey_device.account_id AND m.organization_id = app_current_tenant()
      ));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'session' AND policyname = 'session_isolation') THEN
    CREATE POLICY session_isolation ON session FOR ALL
      USING (app_current_tenant() IS NULL OR EXISTS (
        SELECT 1 FROM member WHERE member.user_id = session.user_id AND member.organization_id = app_current_tenant()
      ))
      WITH CHECK (app_current_tenant() IS NULL OR EXISTS (
        SELECT 1 FROM member WHERE member.user_id = session.user_id AND member.organization_id = app_current_tenant()
      ));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'organization' AND policyname = 'organization_isolation') THEN
    CREATE POLICY organization_isolation ON organization FOR ALL
      USING (app_current_tenant() IS NULL OR id = app_current_tenant())
      WITH CHECK (app_current_tenant() IS NULL OR id = app_current_tenant());
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'api_key' AND policyname = 'api_key_isolation') THEN
    CREATE POLICY api_key_isolation ON api_key FOR ALL
      USING (app_current_tenant() IS NULL OR organization_id = app_current_tenant())
      WITH CHECK (app_current_tenant() IS NULL OR organization_id = app_current_tenant());
  END IF;
END $$;

CREATE OR REPLACE FUNCTION protect_audit_log() RETURNS TRIGGER AS $func$
BEGIN
  RAISE EXCEPTION 'Audit log entries are immutable and cannot be updated or deleted';
END;
$func$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_protect_audit_log ON audit_log;
CREATE TRIGGER trg_protect_audit_log
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION protect_audit_log();
