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
| **`llm_wiki`** | `internal/search/providers_placeholder.go` (`LLMWikiProvider`) | Implemented — Backed by our Local QMD Engine and LLM Wiki microservice |
| `google_okf` | `internal/search/providers_placeholder.go` (`GoogleOKFProvider`) | Implemented — Backed by our Local QMD Engine and Google OKF endpoint |

`llm_wiki` is the default semantic provider. Both implementations leverage our optimized in-memory QMD (Query-Metadata-Document) engine (`internal/search/okf_qmd.go`) for fast local vector and concept similarity search without high infrastructure RAM costs.

Per architectural directives, `pgvector` has been decoupled and removed from retrieval pipelines and ingestion endpoints in favor of purely relying on OpenSearch, LLM Wiki (OKF), and our Local QMD Engine.
