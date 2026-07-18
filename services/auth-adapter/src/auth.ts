import { betterAuth } from "better-auth";
import { jwt } from "better-auth/plugins";
import { Pool } from "pg";

import { config } from "./config.js";

// BetterAuth owns its own Postgres tables (users/sessions/etc, created on
// first run) in the same database as services/auth's hand-rolled `users`
// table — a different table set, so this does not collide with or modify
// services/auth's schema. See README.md "BetterAuth adapter" for the
// still-open question of how/whether the two user stores get reconciled.
export const auth = betterAuth({
  database: new Pool({ connectionString: config.databaseUrl }),
  secret: config.betterAuthSecret,
  baseURL: config.betterAuthUrl,
  emailAndPassword: {
    enabled: true,
  },
  // NOTE: this JWT plugin is BetterAuth's own token issuance (asymmetric
  // algorithms only — EdDSA by default). It is NOT used to produce tokens
  // compatible with apps/api-gateway's existing HS256 middleware; see
  // legacyToken.ts for that bridge.
  plugins: [jwt()],
});
