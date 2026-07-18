package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/openhealthagents/ai-rxos/services/search/internal/config"
	"github.com/openhealthagents/ai-rxos/services/search/internal/handlers"
	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	cfg := config.Load()
	ctx := context.Background()

	osClient, err := search.NewClient(cfg.OpenSearchURL, cfg.OpenSearchUser, cfg.OpenSearchPassword, cfg.IndexName)
	if err != nil {
		slog.Error("opensearch client init failed", "err", err)
		os.Exit(1)
	}
	if err := osClient.EnsureIndex(ctx); err != nil {
		slog.Warn("opensearch index setup failed, continuing", "err", err)
	}

	vectors, err := search.NewRetrievalProvider(ctx, search.ProviderConfig{
		Provider:        cfg.RetrievalProvider,
		DatabaseURL:     cfg.DatabaseURL,
		LLMWikiURL:      cfg.LLMWikiURL,
		LLMWikiAPIKey:   cfg.LLMWikiAPIKey,
		GoogleOKFURL:    cfg.GoogleOKFURL,
		GoogleOKFAPIKey: cfg.GoogleOKFAPIKey,
	})
	if err != nil {
		slog.Error("retrieval provider init failed", "provider", cfg.RetrievalProvider, "err", err)
		os.Exit(1)
	}
	defer vectors.Close()

	h := &handlers.SearchHandler{OpenSearch: osClient, Vectors: vectors, VectorSource: cfg.RetrievalProvider}

	r := chi.NewRouter()
	r.Use(middleware.Recoverer)
	r.Use(middleware.Logger)

	r.Get("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "search"})
	})

	r.Route("/api/v1/search", func(r chi.Router) {
		r.Get("/", h.Query)
		r.Post("/", h.Hybrid)
	})

	slog.Info("search service listening", "port", cfg.Port)
	if err := http.ListenAndServe(":"+cfg.Port, r); err != nil {
		slog.Error("server stopped", "err", err)
		os.Exit(1)
	}
}
