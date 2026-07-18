import { z } from "zod";

/**
 * Shared multi-tenancy conventions for AI-RxOS. This package only defines
 * the contract (naming + types) — it does not enforce anything itself.
 *
 * The Postgres side of this contract lives in each Go service's schema
 * migration (services/auth/internal/store/postgres.go,
 * services/search/internal/search/pgvector.go): both enable Row Level
 * Security with a policy that reads TENANT_SESSION_VARIABLE via
 * Postgres's current_setting(). No caller sets that session variable yet
 * (see README.md "Row Level Security" for what's still required); until
 * one does, the RLS policies fail open and behave exactly as before.
 */

/** Postgres session variable RLS policies key on, set per-request via `SET LOCAL <TENANT_SESSION_VARIABLE> = '<tenantId>'`. */
export const TENANT_SESSION_VARIABLE = "app.tenant_id";

/** HTTP header a gateway/service should use to propagate the resolved tenant downstream. Not yet emitted or read anywhere. */
export const TENANT_ID_HEADER = "X-Organization-Id";

/** JWT claim name a tenant-aware token issuer should use for the tenant id. Not yet emitted by services/auth or services/auth-adapter. */
export const TENANT_ID_CLAIM = "organizationId";

export const TenantIdSchema = z.string().uuid();
export type TenantId = z.infer<typeof TenantIdSchema>;

export interface TenantContext {
  tenantId: TenantId;
}
