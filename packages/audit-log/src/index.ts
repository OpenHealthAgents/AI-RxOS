import { z } from "zod";

/**
 * Shared audit-event contract for AI-RxOS. This package defines the event
 * shape and a pluggable sink interface only — no persistence backend
 * exists yet (no audit table, queue, or consumer exists anywhere in this
 * repo as of this scaffold). Implement AuditLogSink against a real
 * backend (e.g. a Postgres audit_log table, written from within the same
 * request transaction as the action it records) before relying on this
 * for anything.
 */

export const AuditEventSchema = z.object({
  id: z.string().uuid(),
  tenantId: z.string().uuid().optional(),
  actorId: z.string().uuid().optional(),
  action: z.string(),
  resourceType: z.string(),
  resourceId: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
  createdAt: z.string().datetime(),
});
export type AuditEvent = z.infer<typeof AuditEventSchema>;

export interface AuditLogSink {
  record(event: AuditEvent): Promise<void>;
}
