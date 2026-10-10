import crypto from "crypto";
import { dbPool } from "./auth.js";
import { config } from "./config.js";

export interface AuditLogRecord {
  id: string;
  user_id: string | null;
  organization_id: string | null;
  workspace_id: string | null;
  project_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  prev_hash: string | null;
  current_hash: string;
  signature: string;
}

function auditLogHashInput(record: AuditLogRecord): string {
  return [
    record.id,
    record.user_id ?? "",
    record.organization_id ?? "",
    record.workspace_id ?? "",
    record.project_id ?? "",
    record.action,
    record.resource_type,
    record.resource_id ?? "",
    record.ip_address ?? "",
    record.user_agent ?? "",
    JSON.stringify(record.metadata ?? {}),
    record.created_at,
  ].join("|");
}

function computeHash(input: string): string {
  return crypto.createHash("sha256").update(input, "utf8").digest("hex");
}

function computeSignature(hash: string): string {
  return crypto
    .createHmac("sha256", config.auditLogHmacSecret)
    .update(hash, "utf8")
    .digest("hex");
}

export async function verifyAuditLogRecord(recordId: string): Promise<boolean> {
  const result = await dbPool.query<AuditLogRecord>(
    `SELECT id, user_id, organization_id, workspace_id, project_id,
            action, resource_type, resource_id, ip_address, user_agent,
            metadata, created_at, prev_hash, current_hash, signature
      FROM audit_log
      WHERE id = $1`,
    [recordId]
  );

  if (result.rowCount === 0) return false;
  const record = result.rows[0];
  if (!record) return false;

  // Let the database compute the expected hash and signature using the same functions
  const verifyRes = await dbPool.query(
    `SELECT audit_log_compute_hash(audit_log_hash_input(a)) AS expected_hash,
            audit_log_compute_signature(audit_log_compute_hash(audit_log_hash_input(a))) AS expected_signature
     FROM (SELECT * FROM audit_log WHERE id = $1) a`,
    [recordId]
  );

  if (verifyRes.rowCount === 0) return false;
  const { expected_hash, expected_signature } = verifyRes.rows[0] as { expected_hash: string; expected_signature: string };

  if (expected_hash !== record.current_hash) return false;
  if (expected_signature !== record.signature) return false;

  if (record.prev_hash !== null) {
    const prevResult = await dbPool.query<{ current_hash: string }>(
      `SELECT current_hash FROM audit_log WHERE current_hash = $1`,
      [record.prev_hash]
    );
    if (prevResult.rowCount === 0) return false;
  }

  return true;
}
