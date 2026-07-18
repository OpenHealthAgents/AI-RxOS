package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	Port            string
	DatabaseURL     string
	RedisURL        string
	JWTSecret       string
	AccessTokenTTL  time.Duration
	RefreshTokenTTL time.Duration
}

func Load() Config {
	return Config{
		Port:            env("PORT", "8081"),
		DatabaseURL:     env("DATABASE_URL", "postgresql://ai_rxos:changeme@postgres:5432/ai_rxos"),
		RedisURL:        env("REDIS_URL", "redis://redis:6379/0"),
		JWTSecret:       env("JWT_SECRET", "change_this_dev_secret_before_deploying"),
		AccessTokenTTL:  time.Duration(envInt("JWT_ACCESS_TTL_MINUTES", 15)) * time.Minute,
		RefreshTokenTTL: time.Duration(envInt("JWT_REFRESH_TTL_DAYS", 30)) * 24 * time.Hour,
	}
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}
