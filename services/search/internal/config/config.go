package config

import "os"

type Config struct {
	Port               string
	DatabaseURL        string
	OpenSearchURL      string
	OpenSearchUser     string
	OpenSearchPassword string
	IndexName          string

	// RetrievalProvider selects the semantic-search backend behind
	// search.RetrievalProvider (see internal/search/provider.go). Defaults
	// to pgvector; llm_wiki/google_okf are placeholders.
	RetrievalProvider string
	LLMWikiURL        string
	LLMWikiAPIKey     string
	GoogleOKFURL      string
	GoogleOKFAPIKey   string
}

func Load() Config {
	return Config{
		Port:               env("PORT", "8084"),
		DatabaseURL:        env("DATABASE_URL", "postgresql://ai_rxos:changeme@postgres:5432/ai_rxos"),
		OpenSearchURL:      env("OPENSEARCH_URL", "http://opensearch:9200"),
		OpenSearchUser:     env("OPENSEARCH_USER", "admin"),
		OpenSearchPassword: env("OPENSEARCH_PASSWORD", "AiRxOS_Admin1!"),
		IndexName:          env("OPENSEARCH_INDEX", "ai-rxos-documents"),

		RetrievalProvider: env("SEARCH_RETRIEVAL_PROVIDER", "pgvector"),
		LLMWikiURL:        env("LLM_WIKI_URL", ""),
		LLMWikiAPIKey:     env("LLM_WIKI_API_KEY", ""),
		GoogleOKFURL:      env("GOOGLE_OKF_URL", ""),
		GoogleOKFAPIKey:   env("GOOGLE_OKF_API_KEY", ""),
	}
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
