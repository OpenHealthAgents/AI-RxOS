package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/redis/go-redis/v9"

	"github.com/openhealthagents/ai-rxos/services/auth/internal/config"
	"github.com/openhealthagents/ai-rxos/services/auth/internal/handlers"
	"github.com/openhealthagents/ai-rxos/services/auth/internal/store"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	cfg := config.Load()
	ctx := context.Background()

	db, err := store.NewPostgres(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("postgres connection failed", "err", err)
		os.Exit(1)
	}
	defer db.Close()

	opt, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		slog.Error("invalid redis url", "err", err)
		os.Exit(1)
	}
	rdb := redis.NewClient(opt)
	defer rdb.Close()

	h := &handlers.AuthHandler{DB: db, Redis: rdb, Cfg: cfg}

	r := chi.NewRouter()
	r.Use(middleware.Recoverer)
	r.Use(middleware.Logger)

	r.Get("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "auth"})
	})

	r.Route("/api/v1/auth", func(r chi.Router) {
		r.Post("/register", h.Register)
		r.Post("/login", h.Login)
		r.Post("/refresh", h.Refresh)
	})

	slog.Info("auth service listening", "port", cfg.Port)
	if err := http.ListenAndServe(":"+cfg.Port, r); err != nil {
		slog.Error("server stopped", "err", err)
		os.Exit(1)
	}
}
