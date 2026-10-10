import { getRedisClient } from "./rateLimit.js";
import crypto from "crypto";
import { dbPool } from "./auth.js";
import { recordAuditEvent } from "./audit.js";
import { config } from "./config.js";
import { incrementMetric } from "./metrics.js";
import { logInfo, logWarn, logError } from "./logger.js";

interface ScimUser {
  id?: string;
  userName?: string;
  emails?: Array<{ value: string }>;
  displayName?: string;
  groups?: Array<string | { display?: string; value?: string }>;
  active?: boolean;
}

/**
 * SCIM sync task skeleton.
 * This function is intentionally non-destructive and acts as a controlled
 * server-side trigger to perform SCIM provisioning logic. Full SCIM
 * implementation requires per-IdP mapping and secure inbound credentials.
 */
export async function scimSyncForOrganization(organizationId?: string) {
  const redis = await getRedisClient();
  const lockKey = `scim:lock:${organizationId ?? 'global'}`;
  const got = await redis.set(lockKey, '1', { NX: true, EX: 60 });
  if (!got) return { ok: false, message: 'sync_in_progress' };

  try {
    if (!organizationId) {
      // global mode: enumerate orgs and run per-org sync for those with scim enabled
      const all = await dbPool.query(`SELECT id, settings FROM organization`);
      const results: any[] = [];
      for (const r of all.rows) {
        const settings = r.settings ?? {};
        if (settings.scim && settings.scim.enabled) {
          // run per-org sync
          // eslint-disable-next-line no-await-in-loop
          const res = await scimSyncForOrganization(r.id);
          results.push({ org: r.id, result: res });
        }
      }
      return { ok: true, results };
    }

    const r = await dbPool.query(`SELECT id, settings FROM organization WHERE id = $1`, [organizationId]);
    if ((r.rowCount ?? 0) === 0) return { ok: false, message: 'organization_not_found' };
    const settings = r.rows[0].settings ?? {};
    const scimConfig = settings.scim ?? {};
    const summary: any = {
      upserted: 0,
      updated: 0,
      membersAdded: 0,
      membersUpdated: 0,
      orphanedRemoved: 0,
      workspacesSynced: 0,
      projectsSynced: 0,
      pagesFetched: 0,
    };

    incrementMetric('scim.sync.attempt');
    logInfo('SCIM sync started', { organizationId, config: { url: scimConfig.url ? true : false, deltaEnabled: !!scimConfig.deltaEnabled } });

    let scimUsers: ScimUser[] = [];
    if (scimConfig.url) {
      try {
        const since = scimConfig.deltaEnabled ? scimConfig.lastSyncAt : undefined;
        scimUsers = await fetchAllScimUsers(scimConfig.url, scimConfig.bearerToken, scimConfig, since, summary);
      } catch (e) {
        incrementMetric('scim.sync.failure');
        logError('SCIM fetch failed', { organizationId, error: String(e) });
        await recordAuditEvent({ userId: null, organizationId, action: 'scim_fetch_failed', resourceType: 'scim', resourceId: null, ipAddress: null, userAgent: null, metadata: { error: String(e) } });
        return { ok: false, message: 'fetch_failed', error: String(e) };
      }
    } else {
      scimUsers = scimConfig.users ?? [];
    }

    const incomingEmails = new Set<string>();
    for (const su of scimUsers) {
      const email = extractEmail(su);
      if (email) incomingEmails.add(email);
    }

    const existingMembersRes = await dbPool.query(
      `SELECT m.id, m.user_id, m.role, u.email FROM member m JOIN "user" u ON u.id = m.user_id WHERE m.organization_id = $1`,
      [organizationId]
    );
    const existingMembers: Array<{ id: string; user_id: string; role: string; email: string }> = existingMembersRes?.rows ?? [];
    const existingMemberByEmail: Record<string, { id: string; userId: string; role: string }> = {};
    for (const row of existingMembers) {
      existingMemberByEmail[row.email.toLowerCase()] = { id: row.id, userId: row.user_id, role: row.role };
    }

    if (scimConfig.removeOrphanedUsers !== false && config.scimRemoveOrphanedUsers) {
      const orphaned = existingMembers.filter((m) => !incomingEmails.has(m.email.toLowerCase()) && m.role !== 'owner');
      if (orphaned.length > 0) {
        const orphanIds = orphaned.map((m) => m.id);
        await dbPool.query(`DELETE FROM member WHERE id = ANY($1::uuid[])`, [orphanIds]);
        summary.orphanedRemoved = orphaned.length;
      }
    }

    const knownEmails = scimUsers.map((u) => extractEmail(u)).filter(Boolean) as string[];
    const existingUsersRes = await dbPool.query(`SELECT id, email, name FROM "user" WHERE email = ANY($1::text[])`, [knownEmails]);
    const existingUsers: Array<{ id: string; email: string; name: string }> = existingUsersRes?.rows ?? [];
    const userByEmail: Record<string, { id: string; name: string }> = {};
    for (const row of existingUsers) userByEmail[row.email.toLowerCase()] = { id: row.id, name: row.name };

    for (const su of scimUsers) {
      const email = extractEmail(su);
      if (!email) {
        logWarn('SCIM user record missing email', { organizationId, user: su });
        continue;
      }

      const groups = extractGroups(su, scimConfig);
      const desiredRole = determineRoleForUser(groups, scimConfig, su);
      const userId = await createOrUpdateUser(email, su, userByEmail, summary);

      const existingMember = existingMemberByEmail[email];
      if (!existingMember) {
        await dbPool.query(
          `INSERT INTO member (id, organization_id, user_id, role, created_at) VALUES ($1, $2, $3, $4, NOW())`,
          [crypto.randomUUID(), organizationId, userId, desiredRole ?? (scimConfig.defaultRole ?? 'member')]
        );
        summary.membersAdded++;
      } else {
        if (desiredRole && desiredRole !== existingMember.role) {
          await dbPool.query(`UPDATE member SET role = $1, updated_at = NOW() WHERE id = $2`, [desiredRole, existingMember.id]);
          summary.membersUpdated++;
        }
      }

      if (scimConfig.groupWorkspaceMap && typeof scimConfig.groupWorkspaceMap === 'object') {
        for (const group of groups) {
          const mapping = scimConfig.groupWorkspaceMap[group];
          if (mapping && mapping.workspaceId) {
            const added = await syncWorkspaceMember(userId, mapping.workspaceId, mapping.role ?? 'member');
            if (added) summary.workspacesSynced++;
          }
        }
      }

      if (scimConfig.groupProjectMap && typeof scimConfig.groupProjectMap === 'object') {
        for (const group of groups) {
          const mapping = scimConfig.groupProjectMap[group];
          if (mapping && mapping.projectId) {
            const added = await syncProjectMember(userId, mapping.projectId, mapping.role ?? 'member');
            if (added) summary.projectsSynced++;
          }
        }
      }
    }

    if (scimConfig.deltaEnabled) {
      try {
        const newSettings = { ...settings, scim: { ...(settings.scim ?? {}), lastSyncAt: new Date().toISOString() } };
        await dbPool.query(`UPDATE organization SET settings = $1, updated_at = NOW() WHERE id = $2`, [newSettings, organizationId]);
        summary.deltaToken = newSettings.scim.lastSyncAt;
      } catch (e) {
        logWarn('Failed to persist SCIM lastSyncAt', { organizationId, error: String(e) });
      }
    }

    incrementMetric('scim.sync.success');
    incrementMetric('scim.sync.members_added', summary.membersAdded);
    incrementMetric('scim.sync.members_updated', summary.membersUpdated);
    incrementMetric('scim.sync.users_upserted', summary.upserted);
    incrementMetric('scim.sync.users_updated', summary.updated);
    logInfo('SCIM sync completed', { organizationId, summary });
    await recordAuditEvent({ userId: null, organizationId, action: 'scim_sync', resourceType: 'scim', resourceId: null, ipAddress: null, userAgent: null, metadata: summary });
    return { ok: true, message: 'scim_sync_completed', summary };
  } finally {
    await redis.del(lockKey);
  }
}

async function fetchAllScimUsers(url: string, bearerToken?: string, scimConfig?: any, since?: string, summary?: any): Promise<ScimUser[]> {
  const perPage = scimConfig?.perPage ?? 100;
  const results: ScimUser[] = [];
  let nextUrl: string | null = url;
  const maxAttempts = Math.max(1, scimConfig?.retryAttempts ?? 3);
  const backoffBase = Math.max(100, scimConfig?.retryBackoffMs ?? 500);

  while (nextUrl) {
    let attempt = 0;
    let lastErr: any = null;
    while (attempt < maxAttempts) {
      try {
        if (!nextUrl) break;
        const q = new URL(nextUrl);
        if (!q.searchParams.has('startIndex') && !q.searchParams.has('count')) {
          q.searchParams.set('count', String(perPage));
        }
        if (since && scimConfig?.filterTemplate) {
          q.searchParams.set('filter', scimConfig.filterTemplate.replace(/{{\s*since\s*}}/g, encodeURIComponent(since)));
        }
        if (attempt > 0) {
          logWarn('SCIM fetch retry', { nextUrl, attempt: attempt + 1 });
        }
        const requestOptions: any = {
          headers: bearerToken ? { Authorization: `Bearer ${bearerToken}` } : {},
          cache: 'no-store',
        };
        const res = await fetch(q.toString(), requestOptions);
        if (!res.ok) throw new Error(`scim_fetch_failed:${res.status}`);
        const body = (await res.json()) as any;
        const resources: ScimUser[] = body.Resources ?? body.resources ?? [];
        results.push(...resources);
        if (summary) summary.pagesFetched++;

        const links = body.links ?? body.Links ?? null;
        if (Array.isArray(links)) {
          const next = links.find((l: any) => l.rel === 'next' && l.href);
          nextUrl = next ? next.href : null;
        } else if (body.nextLink) {
          nextUrl = body.nextLink;
        } else if (body.totalResults != null && body.startIndex != null) {
          const startIndex = parseInt(body.startIndex, 10);
          if (startIndex + resources.length > body.totalResults) nextUrl = null;
          else {
            const u = new URL(url);
            u.searchParams.set('startIndex', String(startIndex + resources.length));
            u.searchParams.set('count', String(perPage));
            nextUrl = u.toString();
          }
        } else {
          nextUrl = null;
        }

        lastErr = null;
        break;
      } catch (e) {
        lastErr = e;
        attempt++;
        const delay = backoffBase * Math.pow(2, attempt - 1);
        await new Promise((r) => setTimeout(r, delay));
      }
    }
    if (lastErr) throw lastErr;
  }

  return results;
}

function extractEmail(su: ScimUser): string | null {
  const email = su.emails?.[0]?.value?.trim()?.toLowerCase();
  return email || null;
}

function extractGroups(su: ScimUser, scimConfig: any): string[] {
  const groups: string[] = [];
  if (Array.isArray(su.groups)) {
    for (const g of su.groups) {
      if (typeof g === 'string') groups.push(g);
      else if (g && typeof g.display === 'string') groups.push(g.display);
      else if (g && typeof g.value === 'string') groups.push(g.value);
    }
  }

  if (scimConfig?.groups && typeof scimConfig.groups === 'object') {
    const email = extractEmail(su);
    if (email) {
      for (const [groupName, emails] of Object.entries(scimConfig.groups)) {
        if (Array.isArray(emails) && emails.map((x) => x.toLowerCase()).includes(email)) {
          groups.push(groupName);
        }
      }
    }
  }

  return [...new Set(groups)];
}

async function createOrUpdateUser(email: string, su: ScimUser, userByEmail: Record<string, { id: string; name: string }>, summary: any): Promise<string> {
  if (!userByEmail[email]) {
    const userId = crypto.randomUUID();
    await dbPool.query(`INSERT INTO "user" (id, email, name, created_at, updated_at) VALUES ($1, $2, $3, NOW(), NOW())`, [userId, email, su.displayName ?? su.userName ?? email]);
    summary.upserted++;
    userByEmail[email] = { id: userId, name: su.displayName ?? su.userName ?? email };
    return userId;
  }

  const user = userByEmail[email];
  if ((su.displayName ?? su.userName ?? '') && (su.displayName ?? su.userName) !== user.name) {
    await dbPool.query(`UPDATE "user" SET name = $1, updated_at = NOW() WHERE id = $2`, [su.displayName ?? su.userName, user.id]);
    summary.updated++;
    userByEmail[email].name = su.displayName ?? su.userName ?? user.name;
  }
  return user.id;
}

async function syncWorkspaceMember(userId: string, workspaceId: string, role: string): Promise<boolean> {
  const result = await dbPool.query(
    `INSERT INTO workspace_member (id, workspace_id, user_id, role, joined_at) VALUES ($1, $2, $3, $4, NOW()) ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role`,
    [crypto.randomUUID(), workspaceId, userId, role]
  );
  return (result.rowCount ?? 0) > 0;
}

async function syncProjectMember(userId: string, projectId: string, role: string): Promise<boolean> {
  const result = await dbPool.query(
    `INSERT INTO project_member (id, project_id, user_id, role, joined_at) VALUES ($1, $2, $3, $4, NOW()) ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role`,
    [crypto.randomUUID(), projectId, userId, role]
  );
  return (result.rowCount ?? 0) > 0;
}

function determineRoleForUser(groups: string[], scimConfig: any, su: ScimUser): string | undefined {
  const groupRoleMap = scimConfig?.groupRoleMap ?? {};
  for (const [gName, role] of Object.entries(groupRoleMap)) {
    if (groups.includes(gName)) return role as string;
  }
  if (scimConfig?.roleAttribute && typeof (su as any)[scimConfig.roleAttribute] === 'string') {
    return (su as any)[scimConfig.roleAttribute];
  }
  return undefined;
}

export async function scimSyncScheduledTask(organizationId?: string) {
  return scimSyncForOrganization(organizationId);
}

export default { scimSyncForOrganization, scimSyncScheduledTask };
