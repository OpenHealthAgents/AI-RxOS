package config

import "os"

// Config holds the gateway's runtime configuration, sourced entirely from
// environment variables so the same image runs unmodified across
// docker-compose, Kubernetes, and local dev.
type Config struct {
	Port         string
	JWTSecret    string
	AllowOrigins []string

	AuthServiceURL      string
	LiteratureServiceURL string
	KGServiceURL         string
	SearchServiceURL     string
	AgentsServiceURL     string
	WorkflowsServiceURL  string
	ReportsServiceURL    string
	DockingServiceURL    string
	AIServicesURL        string
	KnowledgeServiceURL  string
}

func Load() Config {
	return Config{
		Port:      env("PORT", "8080"),
		JWTSecret: env("JWT_SECRET", "change_this_dev_secret_before_deploying"),
		AllowOrigins: []string{
			env("CORS_ALLOW_ORIGIN", "http://localhost:3000"),
		},
		AuthServiceURL:       env("AUTH_SERVICE_URL", "http://auth:8081"),
		LiteratureServiceURL: env("LITERATURE_SERVICE_URL", "http://literature:8082"),
		KGServiceURL:         env("KG_SERVICE_URL", "http://kg:8083"),
		SearchServiceURL:     env("SEARCH_SERVICE_URL", "http://search:8084"),
		AgentsServiceURL:     env("AGENTS_SERVICE_URL", "http://agents:8085"),
		WorkflowsServiceURL:  env("WORKFLOWS_SERVICE_URL", "http://workflows:8086"),
		ReportsServiceURL:    env("REPORTS_SERVICE_URL", "http://reports:8087"),
		DockingServiceURL:    env("DOCKING_SERVICE_URL", "http://docking:8088"),
		AIServicesURL:        env("AI_SERVICES_URL", "http://ai-services:8090"),
		KnowledgeServiceURL:  env("KNOWLEDGE_SERVICE_URL", "http://knowledge-service:8091"),
	}
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
