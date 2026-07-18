package main

import (
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/openhealthagents/ai-rxos/apps/api-gateway/internal/config"
	"github.com/openhealthagents/ai-rxos/apps/api-gateway/internal/gateway"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))

	cfg := config.Load()
	router := gateway.NewRouter(cfg)

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	slog.Info("api-gateway listening", "port", cfg.Port)
	if err := srv.ListenAndServe(); err != nil {
		slog.Error("server stopped", "err", err)
		os.Exit(1)
	}
}
