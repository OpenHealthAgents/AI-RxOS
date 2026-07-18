# search

Unified search service for the Scientific Search context: `GET /api/v1/search`
does OpenSearch keyword search; `POST /api/v1/search` does hybrid search,
merging OpenSearch keyword hits with a semantic-search backend's hits (pass an
`embedding` array computed upstream by `ai-services`) and ranking by score.

Runs on port **8084**. See `architecture/02-microservices.md` §5.1.

## Retrieval providers

The semantic-search leg of hybrid search is behind an interface,
`search.RetrievalProvider` (`internal/search/provider.go`), selected via
`SEARCH_RETRIEVAL_PROVIDER`:

| Value (default in **bold**) | Implementation | Status |
|---|---|---|
| **`pgvector`** | `internal/search/pgvector.go` (`VectorStore`) | Implemented — Postgres + pgvector, unchanged from before this abstraction existed |
| `llm_wiki` | `internal/search/providers_placeholder.go` (`LLMWikiProvider`) | Placeholder — always returns `ErrProviderNotImplemented` |
| `google_okf` | `internal/search/providers_placeholder.go` (`GoogleOKFProvider`) | Placeholder — always returns `ErrProviderNotImplemented` |

`pgvector` remains the default and the only backend with a real
implementation. The API response shape and every other route are
unchanged regardless of provider — only the `source` field on hits
reflects whichever provider is active.

### Why `llm_wiki` / `google_okf` are placeholders, not real clients

A repo-wide audit found **no existing API contract, SDK, endpoint,
credentials, or documentation** for either "LLM Wiki" or "Google OKF"
anywhere in this codebase or its `architecture/` docs. Rather than invent
one, `LLMWikiProvider`/`GoogleOKFProvider` exist purely as wiring: they
satisfy `RetrievalProvider`, are selectable via config, and fail loudly
(`ErrProviderNotImplemented`) instead of silently returning wrong
results.

Before either can be implemented for real, someone needs to supply:

1. **Which product/API** — "LLM Wiki" and "Google OKF" don't match any
   identifiable product as named. Confirm the exact service (e.g. is
   "Google OKF" the Open Knowledge Foundation, a specific Google API, or
   an internal codename?).
2. **API contract** — base URL, auth method (API key / OAuth / service
   account), request/response schema, rate limits.
3. **Embedding/query compatibility** — what input shape the provider
   expects (raw query text vs. a precomputed embedding vector; if the
   latter, what dimension and model).
4. **Credentials** — provisioned via the secret-management scaffold
   (`infra/helm/ai-rxos/templates/external-secret.yaml`,
   `LLM_WIKI_API_KEY`/`GOOGLE_OKF_API_KEY`).

Implement the real HTTP client inside `LLMWikiProvider.SimilaritySearch` /
`GoogleOKFProvider.SimilaritySearch` in
`internal/search/providers_placeholder.go` once the above is confirmed —
the constructors already read `LLMWikiURL`/`LLMWikiAPIKey` and
`GoogleOKFURL`/`GoogleOKFAPIKey` from config, so only the request/response
handling needs filling in.

## Row Level Security

`document_embeddings` has RLS enabled with a fail-open policy scoped by
an `organization_id` column (see `internal/search/pgvector.go`). No
caller sets the Postgres session variable it checks yet, so behavior is
unchanged from before RLS was added — see the root `README.md` "Row Level
Security" section.
