function requiredEnv(key: string): string {
  const value = process.env[key];

  // In test environments provide safe defaults to allow unit tests to run
  if (!value) {
    if (process.env.NODE_ENV === "test") {
      if (key === "BETTER_AUTH_SECRET") return "test-better-auth-secret";
      if (key === "JWT_SECRET") return "test-jwt-secret";
      if (key === "AUDIT_LOG_HMAC_SECRET") return "test-audit-log-secret";
    }
    throw new Error(`Missing required environment variable: ${key}`);
  }

  return value;
}

function optionalEnv(key: string): string {
  return process.env[key] ?? "";
}

function envWithDefault(key: string, fallback: string): string {
  return process.env[key] ?? fallback;
}


export const config = {

  port: envWithDefault("PORT", "8081"),

  databaseUrl: envWithDefault(
    "DATABASE_URL",
    "postgresql://ai_rxos:changeme@127.0.0.1:15432/ai_rxos"
  ),

  redisUrl: envWithDefault(
    "REDIS_URL",
    "redis://127.0.0.1:6379/0"
  ),


  // Required in production
  betterAuthSecret: requiredEnv(
    "BETTER_AUTH_SECRET"
  ),

  betterAuthUrl: envWithDefault(
    "BETTER_AUTH_URL",
    "http://localhost:8081/api/v1/auth"
  ),


  jwtSecret: requiredEnv(
    "JWT_SECRET"
  ),

  auditLogHmacSecret: envWithDefault(
    "AUDIT_LOG_HMAC_SECRET",
    "local-dev-audit-log-hmac-secret"
  ),

  keyManagementProvider: envWithDefault("KEY_MANAGEMENT_PROVIDER", "auto"),

  jwtAccessTtlMinutes: parseInt(
    envWithDefault("JWT_ACCESS_TTL_MINUTES", "15"),
    10
  ),

  jwtRefreshTtlDays: parseInt(
    envWithDefault("JWT_REFRESH_TTL_DAYS", "30"),
    10
  ),

  // Brute-force protection / account lockout
  // number of failed login attempts before locking
  maxFailedLoginAttempts: parseInt(envWithDefault("MAX_FAILED_LOGIN_ATTEMPTS", "5"), 10),
  // window in seconds to count failed attempts
  failedLoginWindowSeconds: parseInt(envWithDefault("FAILED_LOGIN_WINDOW_SECONDS", "900"), 10),
  // lockout duration in seconds after threshold reached
  accountLockoutSeconds: parseInt(envWithDefault("ACCOUNT_LOCKOUT_SECONDS", "900"), 10),

  // OAuth / OIDC optional for local development

  googleClientId: optionalEnv(
    "GOOGLE_CLIENT_ID"
  ),

  googleClientSecret: optionalEnv(
    "GOOGLE_CLIENT_SECRET"
  ),

  githubClientId: optionalEnv(
    "GITHUB_CLIENT_ID"
  ),

  githubClientSecret: optionalEnv(
    "GITHUB_CLIENT_SECRET"
  ),

  // SCIM sync options
  scimSyncIntervalMinutes: parseInt(envWithDefault("SCIM_SYNC_INTERVAL_MINUTES", "15"), 10),
  scimTokenTtlMinutes: parseInt(envWithDefault("SCIM_TOKEN_TTL_MINUTES", "60"), 10),
  scimRemoveOrphanedUsers: envWithDefault("SCIM_REMOVE_ORPHANED_USERS", "true") === "true",

  // Optional Neo4j URL for scoped graph-based authorization
  neo4jUrl: envWithDefault("NEO4J_URL", ""),
  neo4jUser: optionalEnv("NEO4J_USER"),
  neo4jPassword: optionalEnv("NEO4J_PASSWORD"),
  neo4jEncrypted: envWithDefault("NEO4J_ENCRYPTED", "true") === "true",
  neo4jDatabase: envWithDefault("NEO4J_DATABASE", "neo4j"),
  neo4jPoolSize: parseInt(envWithDefault("NEO4J_POOL_SIZE", "50"), 10),
  neo4jMaxRetryTimeMs: parseInt(envWithDefault("NEO4J_MAX_RETRY_TIME_MS", "30000"), 10),
  // Dynamic client registration: registration access token TTL (0 = never expire)
  registrationTokenTtlSeconds: parseInt(envWithDefault("REGISTRATION_TOKEN_TTL_SECONDS", "0"), 10),
  // JWKS cache TTL for OIDC provider JWKS fetches
  oidcJwksCacheTtlSeconds: parseInt(envWithDefault("OIDC_JWKS_CACHE_TTL_SECONDS", "3600"), 10),
  oidcJwksRefreshWindowSeconds: parseInt(envWithDefault("OIDC_JWKS_REFRESH_WINDOW_SECONDS", "60"), 10),

  rateLimitFailClosed: envWithDefault("RATE_LIMIT_FAIL_CLOSED", "false") === "true",
};