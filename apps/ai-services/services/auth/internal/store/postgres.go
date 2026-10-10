package store

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Row Level Security is scaffolded here rather than enforced end-to-end:
// app_current_tenant() falls back to NULL (allow all rows) until a caller
// actually runs "SET LOCAL app.tenant_id = '<uuid>'" per request, so this
// is safe to enable ahead of that wiring — see packages/tenancy and
// README.md "Row Level Security". FORCE (not just ENABLE) is required
// because the connecting role owns the table, and table owners bypass
// RLS unless forced.
const schema = `
CREATE TABLE IF NOT EXISTS users (
	id UUID PRIMARY KEY,
	email TEXT UNIQUE NOT NULL,
	password_hash TEXT NOT NULL,
	display_name TEXT NOT NULL,
	organization_id UUID NOT NULL,
	roles TEXT[] NOT NULL DEFAULT '{}',
	created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Wrapped in a DO block with an exception handler because multiple
-- services race to create this same function on first boot; concurrent
-- "CREATE OR REPLACE FUNCTION" calls can still hit a unique_violation on
-- pg_proc even though OR REPLACE is used (a well-known Postgres race).
DO $migrate$
BEGIN
	CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS uuid AS $func$
		SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
	$func$ LANGUAGE sql STABLE;
EXCEPTION WHEN duplicate_function OR unique_violation THEN
	NULL;
END
$migrate$;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1 FROM pg_policies WHERE tablename = 'users' AND policyname = 'users_tenant_isolation'
	) THEN
		CREATE POLICY users_tenant_isolation ON users
			USING (app_current_tenant() IS NULL OR organization_id = app_current_tenant());
	END IF;
END $$;
`

type Postgres struct {
	Pool *pgxpool.Pool
}

func NewPostgres(ctx context.Context, url string) (*Postgres, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		return nil, err
	}
	if _, err := pool.Exec(ctx, schema); err != nil {
		return nil, err
	}
	return &Postgres{Pool: pool}, nil
}

func (p *Postgres) Close() {
	p.Pool.Close()
}
