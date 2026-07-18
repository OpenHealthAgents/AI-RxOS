package gateway

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"

	"github.com/openhealthagents/ai-rxos/apps/api-gateway/internal/config"
)

// publicPaths bypass JWT validation: health checks plus the auth service's
// own login/register/refresh endpoints (you can't require a token to get one).
var publicPaths = []string{
	"/healthz",
	"/readyz",
	"/api/v1/auth/login",
	"/api/v1/auth/register",
	"/api/v1/auth/refresh",
}

// NewRouter wires the full routing table: cross-cutting middleware, then a
// reverse-proxy route per backend service, keyed by URL prefix.
func NewRouter(cfg config.Config) http.Handler {
	r := chi.NewRouter()

	r.Use(middleware.Recoverer)
	r.Use(requestLogger)
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   cfg.AllowOrigins,
		AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Content-Type", "Authorization"},
		AllowCredentials: true,
	}))

	limiter := newIPRateLimiter(20, 40)
	r.Use(limiter.middleware)
	r.Use(jwtAuth(cfg.JWTSecret, publicPaths))

	r.Get("/healthz", healthHandler)
	r.Get("/readyz", healthHandler)

	routes := map[string]string{
		"/api/v1/auth":            cfg.AuthServiceURL,
		"/api/v1/organizations":   cfg.AuthServiceURL,
		"/api/v1/papers":          cfg.LiteratureServiceURL,
		"/api/v1/ingestion":       cfg.LiteratureServiceURL,
		"/api/v1/graph":           cfg.KGServiceURL,
		"/api/v1/ontologies":      cfg.KGServiceURL,
		"/api/v1/search":          cfg.SearchServiceURL,
		"/api/v1/agents":          cfg.AgentsServiceURL,
		"/api/v1/workflows":       cfg.WorkflowsServiceURL,
		"/api/v1/reports":         cfg.ReportsServiceURL,
		"/api/v1/molecules":       cfg.DockingServiceURL,
		"/api/v1/docking":         cfg.DockingServiceURL,
		"/api/v1/ai":              cfg.AIServicesURL,
		"/api/v1/knowledge":       cfg.KnowledgeServiceURL,
	}

	for prefix, target := range routes {
		proxy := newReverseProxy(prefix, target)
		r.Mount(prefix, http.StripPrefix("", proxy))
	}

	return r
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{
		"status":  "ok",
		"service": "api-gateway",
	})
}
