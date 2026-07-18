package search

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

// VectorStore wraps pgvector similarity search over the
// document_embeddings table (embedding column: vector(768)).
type VectorStore struct {
	pool *pgxpool.Pool
}

// Row Level Security is scaffolded here rather than enforced end-to-end:
// app_current_tenant() falls back to NULL (allow all rows) until a caller
// actually runs "SET LOCAL app.tenant_id = '<uuid>'" per request, so this
// is safe to enable ahead of that wiring — see packages/tenancy and
// README.md "Row Level Security". organization_id is nullable/unused by
// Upsert today; it exists so the policy has something to scope once a
// caller starts populating it.
const schema = `
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS document_embeddings (
	id TEXT PRIMARY KEY,
	title TEXT NOT NULL,
	content TEXT NOT NULL,
	embedding vector(768) NOT NULL
);
CREATE INDEX IF NOT EXISTS document_embeddings_embedding_idx
	ON document_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ALTER TABLE document_embeddings ADD COLUMN IF NOT EXISTS organization_id UUID;

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

ALTER TABLE document_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_embeddings FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1 FROM pg_policies WHERE tablename = 'document_embeddings' AND policyname = 'document_embeddings_tenant_isolation'
	) THEN
		CREATE POLICY document_embeddings_tenant_isolation ON document_embeddings
			USING (app_current_tenant() IS NULL OR organization_id = app_current_tenant());
	END IF;
END $$;
`

func NewVectorStore(ctx context.Context, databaseURL string) (*VectorStore, error) {
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		return nil, err
	}
	if _, err := pool.Exec(ctx, schema); err != nil {
		return nil, err
	}
	return &VectorStore{pool: pool}, nil
}

func (v *VectorStore) Close() {
	v.pool.Close()
}

func (v *VectorStore) Upsert(ctx context.Context, id, title, content string, embedding []float32) error {
	_, err := v.pool.Exec(ctx,
		`INSERT INTO document_embeddings (id, title, content, embedding)
		 VALUES ($1, $2, $3, $4)
		 ON CONFLICT (id) DO UPDATE SET title = $2, content = $3, embedding = $4`,
		id, title, content, vectorLiteral(embedding),
	)
	return err
}

func (v *VectorStore) SimilaritySearch(ctx context.Context, embedding []float32, limit int) ([]Hit, error) {
	rows, err := v.pool.Query(ctx,
		`SELECT id, title, content, 1 - (embedding <=> $1) AS similarity
		 FROM document_embeddings
		 ORDER BY embedding <=> $1
		 LIMIT $2`,
		vectorLiteral(embedding), limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var hits []Hit
	for rows.Next() {
		var h Hit
		if err := rows.Scan(&h.ID, &h.Title, &h.Snippet, &h.Score); err != nil {
			return nil, err
		}
		hits = append(hits, h)
	}
	return hits, rows.Err()
}

// vectorLiteral renders a float32 slice as pgvector's text input format,
// e.g. "[0.1,0.2,0.3]".
func vectorLiteral(v []float32) string {
	parts := make([]string, len(v))
	for i, f := range v {
		parts[i] = strconv.FormatFloat(float64(f), 'f', -1, 32)
	}
	return fmt.Sprintf("[%s]", strings.Join(parts, ","))
}
