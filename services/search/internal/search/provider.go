package search

import (
	"context"
	"fmt"
)

// RetrievalProvider is the abstraction the hybrid search handler uses for
// the semantic/vector leg of a search (as opposed to OpenSearch's keyword
// leg). LLMWikiProvider and GoogleOKFProvider implement high-speed
// retrieval using our Local QMD Engine and OKF microservices.
type RetrievalProvider interface {
	SimilaritySearch(ctx context.Context, embedding []float32, limit int) ([]Hit, error)
	Upsert(ctx context.Context, id, title, content string, embedding []float32) error
	Close()
}

const (
	ProviderLLMWiki   = "llm_wiki"
	ProviderGoogleOKF = "google_okf"
)

// ProviderConfig carries the settings needed to construct any
// RetrievalProvider implementation, selected by NewRetrievalProvider.
type ProviderConfig struct {
	Provider string

	// llm_wiki
	LLMWikiURL    string
	LLMWikiAPIKey string

	// google_okf
	GoogleOKFURL    string
	GoogleOKFAPIKey string

	// Advanced hybrid search config
	KGServiceURL  string
	OKFBundlePath string
	ShardCount    int
	Replicas      int
	WeightBM25     float64
	WeightVector   float64
	WeightGraph    float64
	WeightCitation float64
	RRFConstantK   int
}

// NewRetrievalProvider builds the RetrievalProvider selected by
// cfg.Provider (env var SEARCH_RETRIEVAL_PROVIDER). llm_wiki is the
// default semantic provider.
func NewRetrievalProvider(ctx context.Context, cfg ProviderConfig) (RetrievalProvider, error) {
	switch cfg.Provider {
	case "", ProviderLLMWiki:
		return NewLLMWikiProvider(cfg)
	case ProviderGoogleOKF:
		return NewGoogleOKFProvider(cfg)
	default:
		return nil, fmt.Errorf("unknown SEARCH_RETRIEVAL_PROVIDER %q (want %q or %q)",
			cfg.Provider, ProviderLLMWiki, ProviderGoogleOKF)
	}
}
