import type { QueryConfig, QueryResult, QueryResultRow } from 'pg';
import { dbPool } from './auth.js';
import { getCurrentTenantOrganizationId, runWithTenantOrganizationId } from './tenantContext.js';

export async function query<T extends QueryResultRow = any>(text: string | QueryConfig, params?: unknown[]): Promise<QueryResult<T>> {
  const organizationId = getCurrentTenantOrganizationId();
  if (!organizationId) {
    return dbPool.query<T>(text as string, params);
  }

  const client = await dbPool.connect();
  try {
    await client.query('SET LOCAL app.organization_id = $1', [organizationId]);
    return client.query<T>(text as string, params);
  } finally {
    client.release();
  }
}

export async function withTenant<T>(organizationId: string | null, fn: () => Promise<T>): Promise<T> {
  return runWithTenantOrganizationId(organizationId, fn);
}
