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

	osClient, err := search.NewClientWithScalingAndCACert(
		cfg.OpenSearchURL,
		cfg.OpenSearchUser,
		cfg.OpenSearchPassword,
		cfg.IndexName,
		cfg.ShardCount,
		cfg.Replicas,
		cfg.OpenSearchCACert,
	)
	if err != nil {
		slog.Error("opensearch client init failed", "err", err)
		os.Exit(1)
	}
	if err := osClient.EnsureIndex(ctx); err != nil {
		slog.Warn("opensearch index setup failed, continuing", "err", err)
	}

	vectors, err := search.NewRetrievalProvider(ctx, search.ProviderConfig{
		Provider:        cfg.RetrievalProvider,
		LLMWikiURL:      cfg.LLMWikiURL,
		LLMWikiAPIKey:   cfg.LLMWikiAPIKey,
		GoogleOKFURL:    cfg.GoogleOKFURL,
		GoogleOKFAPIKey: cfg.GoogleOKFAPIKey,
		KGServiceURL:    cfg.KGServiceURL,
		OKFBundlePath:   cfg.OKFBundlePath,
		ShardCount:      cfg.ShardCount,
		Replicas:        cfg.Replicas,
		WeightBM25:      cfg.WeightBM25,
		WeightVector:    cfg.WeightVector,
		WeightGraph:     cfg.WeightGraph,
		WeightCitation:  cfg.WeightCitation,
		RRFConstantK:    cfg.RRFConstantK,
	})
	if err != nil {
		slog.Error("retrieval provider init failed", "provider", cfg.RetrievalProvider, "err", err)
		os.Exit(1)
	}
	defer vectors.Close()

	citations := search.NewCitationSearcher()
	graph := search.NewGraphSearcher(cfg.KGServiceURL, cfg.InternalToken)
	ranker := search.NewResultRanker(
		cfg.RRFConstantK,
		cfg.WeightBM25,
		cfg.WeightVector,
		cfg.WeightGraph,
		cfg.WeightCitation,
	)

	h := &handlers.SearchHandler{
		OpenSearch:    osClient,
		Vectors:       vectors,
		VectorSource:  cfg.RetrievalProvider,
		InternalToken: cfg.InternalToken,
		Citations:     citations,
		Graph:         graph,
		Canonical:     search.NewCanonicalContextClient(cfg.KGServiceURL, cfg.InternalToken),
		Ranker:        ranker,
	}

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
		r.Post("/index", h.Index)
		r.Post("/context", h.Context)
		r.Get("/stream", h.StreamQuery)
		r.Post("/stream", h.StreamHybrid)
	})

	slog.Info("search service listening", "port", cfg.Port, "provider", cfg.RetrievalProvider, "shards", cfg.ShardCount)
	if err := http.ListenAndServe(":"+cfg.Port, r); err != nil {
		slog.Error("server stopped", "err", err)
		os.Exit(1)
	}
}
