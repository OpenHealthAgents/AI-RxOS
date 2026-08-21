-- LLM Wiki service schema.
--
-- Additive only: lives in its own `llm_wiki` schema inside the shared
-- ai_rxos Postgres database (the same instance every other AI-RxOS service
-- already uses via DATABASE_URL) and never touches a table owned by
-- another service (auth's `public` schema tables, etc.).
CREATE SCHEMA IF NOT EXISTS llm_wiki;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Session-local tenant scope, set by the application on every connection
-- before it runs a query (see app/db/pool.py::tenant_connection). This
-- compares against a text GUC rather than a uuid foreign key the way
-- services/auth's app_current_tenant() does, because organization_id here
-- is an opaque caller-supplied string (from the wiki write/query payload),
-- not a row this database owns.
CREATE OR REPLACE FUNCTION llm_wiki.current_tenant() RETURNS text AS $$
  SELECT NULLIF(current_setting('app.wiki_organization_id', true), '')
$$ LANGUAGE sql STABLE;

CREATE TABLE IF NOT EXISTS llm_wiki.wiki_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id TEXT,
    workspace_id TEXT,
    project_id TEXT,
    category TEXT NOT NULL,
    slug TEXT NOT NULL,
    entity_id TEXT,
    title TEXT,
    current_version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- NULLs are never equal under a plain UNIQUE constraint, so an untenanted
-- page (organization_id/workspace_id both NULL, matching wiki_client.py's
-- pre-Prompt-8 untenanted path) would otherwise never collide with itself
-- on repeated writes. Coalescing to '' makes the natural key
-- (org, workspace, category, slug) unique in every case.
CREATE UNIQUE INDEX IF NOT EXISTS wiki_pages_natural_key
    ON llm_wiki.wiki_pages (
        COALESCE(organization_id, ''),
        COALESCE(workspace_id, ''),
        category,
        slug
    );

CREATE INDEX IF NOT EXISTS wiki_pages_org_idx ON llm_wiki.wiki_pages (organization_id);
CREATE INDEX IF NOT EXISTS wiki_pages_updated_idx ON llm_wiki.wiki_pages (updated_at DESC);

CREATE TABLE IF NOT EXISTS llm_wiki.wiki_page_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id UUID NOT NULL REFERENCES llm_wiki.wiki_pages(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    document JSONB NOT NULL DEFAULT '{}'::jsonb,
    entity JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    relationships JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (page_id, version)
);

CREATE INDEX IF NOT EXISTS wiki_page_versions_page_idx
    ON llm_wiki.wiki_page_versions (page_id, version DESC);

ALTER TABLE llm_wiki.wiki_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_wiki.wiki_pages FORCE ROW LEVEL SECURITY;
ALTER TABLE llm_wiki.wiki_page_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_wiki.wiki_page_versions FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname = 'llm_wiki' AND tablename = 'wiki_pages' AND policyname = 'wiki_pages_isolation'
  ) THEN
    -- A page is visible/writable when it's untenanted (global, pre-Prompt-8
    -- content) or when it belongs to the caller's own organization. Unlike
    -- services/auth's admin-bypass RLS pattern, a request with no
    -- organization in scope (current_tenant() IS NULL) does NOT see every
    -- tenant's data -- it only ever sees untenanted pages. This is
    -- defense-in-depth: the application layer applies the same filter
    -- explicitly on every query regardless of RLS being enabled.
    CREATE POLICY wiki_pages_isolation ON llm_wiki.wiki_pages FOR ALL
      USING (organization_id IS NULL OR organization_id = llm_wiki.current_tenant())
      WITH CHECK (organization_id IS NULL OR organization_id = llm_wiki.current_tenant());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname = 'llm_wiki' AND tablename = 'wiki_page_versions' AND policyname = 'wiki_page_versions_isolation'
  ) THEN
    CREATE POLICY wiki_page_versions_isolation ON llm_wiki.wiki_page_versions FOR ALL
      USING (EXISTS (
        SELECT 1 FROM llm_wiki.wiki_pages p WHERE p.id = wiki_page_versions.page_id
          AND (p.organization_id IS NULL OR p.organization_id = llm_wiki.current_tenant())
      ))
      WITH CHECK (EXISTS (
        SELECT 1 FROM llm_wiki.wiki_pages p WHERE p.id = wiki_page_versions.page_id
          AND (p.organization_id IS NULL OR p.organization_id = llm_wiki.current_tenant())
      ));
  END IF;
END $$;
