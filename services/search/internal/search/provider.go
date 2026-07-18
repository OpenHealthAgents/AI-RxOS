package search

import (
	"context"
	"fmt"
)

// RetrievalProvider is the abstraction the hybrid search handler uses for
// the semantic/vector leg of a search (as opposed to OpenSearch's keyword
// leg). VectorStore (pgvector) is the default, backwards-compatible
// implementation. LLMWikiProvider and GoogleOKFProvider are placeholders
// reserved for a future migration away from pgvector — see README.md
// "Retrieval providers" for exactly what's needed before they can be
// wired up for real.
type RetrievalProvider interface {
	SimilaritySearch(ctx context.Context, embedding []float32, limit int) ([]Hit, error)
	Close()
}

const (
	ProviderPgvector  = "pgvector"
	ProviderLLMWiki   = "llm_wiki"
	ProviderGoogleOKF = "google_okf"
)

// ProviderConfig carries the settings needed to construct any
// RetrievalProvider implementation, selected by NewRetrievalProvider.
type ProviderConfig struct {
	Provider string

	// pgvector
	DatabaseURL string

	// llm_wiki (placeholder — see LLMWikiProvider)
	LLMWikiURL    string
	LLMWikiAPIKey string

	// google_okf (placeholder — see GoogleOKFProvider)
	GoogleOKFURL    string
	GoogleOKFAPIKey string
}

// NewRetrievalProvider builds the RetrievalProvider selected by
// cfg.Provider (env var SEARCH_RETRIEVAL_PROVIDER). pgvector remains the
// default until real LLM Wiki / Google OKF integration details (API
// contract, auth, SDK) are available.
func NewRetrievalProvider(ctx context.Context, cfg ProviderConfig) (RetrievalProvider, error) {
	switch cfg.Provider {
	case "", ProviderPgvector:
		return NewVectorStore(ctx, cfg.DatabaseURL)
	case ProviderLLMWiki:
		return NewLLMWikiProvider(cfg)
	case ProviderGoogleOKF:
		return NewGoogleOKFProvider(cfg)
	default:
		return nil, fmt.Errorf("unknown SEARCH_RETRIEVAL_PROVIDER %q (want %q, %q, or %q)",
			cfg.Provider, ProviderPgvector, ProviderLLMWiki, ProviderGoogleOKF)
	}
}
