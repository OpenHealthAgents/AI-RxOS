import { betterAuth } from "better-auth";
import { admin, organization, twoFactor } from "better-auth/plugins";
import { passkey } from "@better-auth/passkey";
import { apiKey } from "@better-auth/api-key";
import { sso } from "@better-auth/sso";
import { scim } from "@better-auth/scim";
import pg from "pg";
import { config } from "./config.js";
import { getCurrentTenantOrganizationId } from "./tenantContext.js";
import type { QueryConfig, QueryResult, QueryResultRow } from "pg";

export const dbPool = new pg.Pool({
  connectionString: config.databaseUrl,
});

const originalDbPoolQuery = dbPool.query.bind(dbPool) as (
  text: string | QueryConfig,
  params?: unknown[] | undefined,
) => Promise<QueryResult<any>>;
const originalDbPoolConnect = dbPool.connect.bind(dbPool) as () => Promise<pg.PoolClient>;

;(dbPool as any).connect = async function connect(): Promise<pg.PoolClient> {
  const client = await originalDbPoolConnect();
  const organizationId = getCurrentTenantOrganizationId();

  try {
    await client.query("SELECT set_config('audit.log_hmac_secret', $1, false)", [config.auditLogHmacSecret]);
    await client.query("SELECT set_config('app.organization_id', $1, false)", [organizationId ?? ""]);
  } catch (err) {
    client.release(true);
    throw err;
  }

  const originalRelease = client.release.bind(client);
  let resetDone = false;

  client.release = async function () {
    if (!resetDone) {
      try {
        await client.query("SELECT set_config('app.organization_id', '', false)");
        await client.query("RESET audit.log_hmac_secret");
      } catch {
        originalRelease(true);
        throw new Error("Failed to reset database security context before releasing a connection");
      }
      resetDone = true;
    }
    originalRelease();
  };
  return client;
};

;(dbPool as any).query = async function query<T extends QueryResultRow = any>(
  text: string | QueryConfig,
  params?: unknown[]
): Promise<QueryResult<T>> {
  const organizationId = getCurrentTenantOrganizationId();

  const client = await originalDbPoolConnect();
  try {
    await client.query("SELECT set_config('audit.log_hmac_secret', $1, false)", [config.auditLogHmacSecret]);
    await client.query("SELECT set_config('app.organization_id', $1, false)", [organizationId ?? ""]);

    return client.query<T>(text as string, params);
  } finally {
    try {
      await client.query("SELECT set_config('app.organization_id', '', false)");
      await client.query("RESET audit.log_hmac_secret");
    } catch {
      client.release(true);
      throw new Error("Failed to reset database security context before releasing a connection");
    }
    client.release();
  }
};

export const auth = betterAuth({
  database: dbPool,
  secret: config.betterAuthSecret,
  baseURL: config.betterAuthUrl,

  emailAndPassword: {
    enabled: true,
  },

  // BetterAuth v1.6.23: generateId moved into advanced.database.generateId
  // Using "uuid" shorthand: instructs BetterAuth to generate UUIDs per-row
  // (uses gen_random_uuid() for PostgreSQL).
  // Remove this block if you want BetterAuth's default random ID generation.
  advanced: {
    database: {
      generateId: "uuid",
    },
  },

  socialProviders: {
    ...(config.googleClientId && config.googleClientSecret
      ? {
          google: {
            clientId: config.googleClientId,
            clientSecret: config.googleClientSecret,
          },
        }
      : {}),
    ...(config.githubClientId && config.githubClientSecret
      ? {
          github: {
            clientId: config.githubClientId,
            clientSecret: config.githubClientSecret,
          },
        }
      : {}),
  },

  plugins: [
    admin(),
    // Organization plugin: allowUserToCreateOrganization is the correct v1.6.23 name.
    // (The old name was allowMemberToCreateOrganization - renamed in this version.)
    organization({
      allowUserToCreateOrganization: true,
    }),
    twoFactor(),
    passkey(),
    // API Key plugin: references is a property of ApiKeyConfigurationOptions.
    // "organization" means keys are owned by an organization, not a user.
    apiKey({
      references: "organization",
    }),
    sso(),
    scim(),
  ],
});

export type Auth = typeof auth;
