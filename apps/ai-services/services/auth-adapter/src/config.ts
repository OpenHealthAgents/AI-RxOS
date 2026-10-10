function env(key: string, fallback: string): string {
  const v = process.env[key];
  return v && v.length > 0 ? v : fallback;
}

export const config = {
  port: env("PORT", "8089"),
  databaseUrl: env("DATABASE_URL", "postgresql://ai_rxos:changeme@postgres:5432/ai_rxos"),

  // BetterAuth's own config (session cookies, its own JWT plugin, etc).
  betterAuthSecret: env("BETTER_AUTH_SECRET", "change_this_dev_secret_before_deploying"),
  betterAuthUrl: env("BETTER_AUTH_URL", `http://localhost:${env("PORT", "8089")}`),

  // Shared with services/auth (internal/config/config.go) so
  // signLegacyAccessToken (see legacyToken.ts) mints tokens
  // apps/api-gateway's existing jwtAuth middleware already accepts.
  jwtSecret: env("JWT_SECRET", "change_this_dev_secret_before_deploying"),
  jwtAccessTtlMinutes: parseInt(env("JWT_ACCESS_TTL_MINUTES", "15"), 10),
};
