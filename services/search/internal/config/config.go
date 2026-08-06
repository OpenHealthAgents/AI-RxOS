package config

import (
	"os"
	"strconv"
)

type Config struct {
	Port               string
	OpenSearchURL      string
	OpenSearchUser     string
	OpenSearchPassword string
	IndexName          string

	// RetrievalProvider selects the semantic-search backend behind
	// search.RetrievalProvider (see internal/search/provider.go). Defaults
	// to llm_wiki; backed by local QMD engine or OKF microservice.
	RetrievalProvider string
	LLMWikiURL        string
	LLMWikiAPIKey     string
	GoogleOKFURL      string
	GoogleOKFAPIKey   string

	// Advanced search and ranking configuration
	KGServiceURL  string
	OKFBundlePath string
	ShardCount    int
	Replicas      int

	// Hybrid ranking weights & parameters
	WeightBM25     float64
	WeightVector   float64
	WeightGraph    float64
	WeightCitation float64
	RRFConstantK   int
}

func Load() Config {
	return Config{
		Port:               env("PORT", "8084"),
		OpenSearchURL:      env("OPENSEARCH_URL", "http://opensearch:9200"),
		OpenSearchUser:     env("OPENSEARCH_USER", "admin"),
		OpenSearchPassword: env("OPENSEARCH_PASSWORD", "AiRxOS_Admin1!"),
		IndexName:          env("OPENSEARCH_INDEX", "ai-rxos-documents"),

		RetrievalProvider: env("SEARCH_RETRIEVAL_PROVIDER", "llm_wiki"),
		LLMWikiURL:        env("LLM_WIKI_URL", "http://llmwiki:8086"),
		LLMWikiAPIKey:     env("LLM_WIKI_API_KEY", ""),
		GoogleOKFURL:      env("GOOGLE_OKF_URL", "http://llmwiki:8086"),
		GoogleOKFAPIKey:   env("GOOGLE_OKF_API_KEY", ""),

		KGServiceURL:  env("KG_SERVICE_URL", "http://kg:8083"),
		OKFBundlePath: env("OKF_BUNDLE_PATH", "/var/data/okf_wiki"),
		ShardCount:    envInt("OPENSEARCH_SHARD_COUNT", 16),
		Replicas:      envInt("OPENSEARCH_REPLICAS", 1),

		WeightBM25:     envFloat("SEARCH_WEIGHT_BM25", 0.35),
		WeightVector:   envFloat("SEARCH_WEIGHT_VECTOR", 0.35),
		WeightGraph:    envFloat("SEARCH_WEIGHT_GRAPH", 0.15),
		WeightCitation: envFloat("SEARCH_WEIGHT_CITATION", 0.15),
		RRFConstantK:   envInt("SEARCH_RRF_K", 60),
	}
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
	}
	return fallback
}

func envFloat(key string, fallback float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return fallback
}
