import { dbPool } from "./auth.js";

export interface AuditLogParams {
  userId?: string | null;
  organizationId?: string | null;
  workspaceId?: string | null;
  projectId?: string | null;
  action: string;
  resourceType: string;
  resourceId?: string | null;
  ipAddress?: string | null;
  userAgent?: string | null;
  metadata?: Record<string, any>;
}

/**
 * Audit Log Writer (HIPAA and SOC2 compliant)
 * Appends actions directly into the audit_log table. Immutability is enforced
 * at the database layer via triggers which reject UPDATE or DELETE operations.
 */
export async function recordAuditEvent(params: AuditLogParams): Promise<void> {
  const query = `
    INSERT INTO audit_log (
      user_id, organization_id, workspace_id, project_id,
      action, resource_type, resource_id, ip_address, user_agent, metadata
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
  `;
  const values = [
    params.userId || null,
    params.organizationId || null,
    params.workspaceId || null,
    params.projectId || null,
    params.action,
    params.resourceType,
    params.resourceId || null,
    params.ipAddress || null,
    params.userAgent || null,
    JSON.stringify(params.metadata || {}),
  ];

  try {
    await dbPool.query(query, values);
  } catch (err) {
    // Critical audit log failure alert
    // eslint-disable-next-line no-console
    console.error("COMPLIANCE CRITICAL: Failed to write to audit log:", err);
  }
}
