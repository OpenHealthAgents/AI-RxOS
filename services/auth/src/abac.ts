export interface SubjectAttributes {
  id: string;
  roles: string[];
  clearanceLevel: number; // 1 = public, 2 = internal, 3 = restricted, 4 = confidential/secret
  department?: string;
  organizationId?: string;
}

export interface ResourceAttributes {
  ownerId?: string;
  organizationId?: string;
  workspaceId?: string;
  projectId?: string;
  sensitivityLevel: number;
  isLocked?: boolean;
}

export type Action = "read" | "write" | "delete" | "share";

export interface EnvironmentAttributes {
  ipAddress?: string;
  timeOfDay?: string; // Format: "HH:MM"
}

export interface ABACRequest {
  subject: SubjectAttributes;
  resource: ResourceAttributes;
  action: Action;
  environment?: EnvironmentAttributes;
}

export interface ABACResult {
  allowed: boolean;
  reason?: string;
}

/**
 * ABAC Policy Engine - Evaluates complex, attribute-based policy rules for security clearance,
 * resource lock states, tenant boundary enforcement, and environment constraints.
 */
import { isAllowedByNeo4j } from "./neo4j.js";

export async function evaluateABAC(req: ABACRequest): Promise<ABACResult> {
  const { subject, resource, action, environment } = req;

  // 1. Enforce strict Tenant Isolation at the application level
  if (resource.organizationId && subject.organizationId && resource.organizationId !== subject.organizationId) {
    return {
      allowed: false,
      reason: "Access denied. Cross-tenant resources cannot be accessed.",
    };
  }

  // 2. Organization Admin Bypass
  if (subject.roles.includes("admin") || subject.roles.includes("owner")) {
    return { allowed: true };
  }

  // 3. Resource Modification Lock check
  if (resource.isLocked && action !== "read") {
    return {
      allowed: false,
      reason: "Access denied. Resource is locked for edits.",
    };
  }

  const isOwner = resource.ownerId === subject.id;

  // 4. Deletion restriction: Only resource owner or organization admin can delete
  if (action === "delete") {
    if (!isOwner) {
      return {
        allowed: false,
        reason: "Access denied. Only the resource owner can perform deletions.",
      };
    }
  }

  // 5. Sensitivity and Security Clearance Level validation
  if (subject.clearanceLevel < resource.sensitivityLevel) {
    return {
      allowed: false,
      reason: `Access denied. Insufficient clearance level (Required: ${resource.sensitivityLevel}, Subject: ${subject.clearanceLevel}).`,
    };
  }

  // 6. Write operations: Guest check
  if (action === "write") {
    if (subject.roles.includes("guest") || subject.roles.length === 0) {
      return {
        allowed: false,
        reason: "Access denied. Guest users are not authorized to write or modify data.",
      };
    }
  }

  // 7. Sharing Restrictions for highly sensitive data
  if (action === "share") {
    if (resource.sensitivityLevel >= 3 && !isOwner) {
      return {
        allowed: false,
        reason: "Access denied. Only the resource owner is allowed to share sensitive data.",
      };
    }
  }

  // 8. Environmental constraint validation
  if (resource.sensitivityLevel >= 4 && environment?.timeOfDay) {
    const time = environment?.timeOfDay ?? "00:00";
const hour = Number(time.split(":").at(0) ?? "00");
    if (hour < 6 || hour > 22) {
      return {
        allowed: false,
        reason: "Access denied. Confidential resources can only be accessed during working hours (06:00-22:00).",
      };
    }
  }

  // 9. Optional: Consult Neo4j for graph-scoped policies when configured
  try {
    const neo = await isAllowedByNeo4j(
      subject.id,
      resource.projectId ?? resource.workspaceId ?? resource.ownerId ?? "",
      action,
      subject.organizationId
    );
    if (neo.available) {
      if (!neo.allowed) {
        return { allowed: false, reason: neo.reason };
      }
    }
  } catch (e) {
    // ignore neo4j failures and fail-open
    // eslint-disable-next-line no-console
    console.error("ABAC: Neo4j check failed:", e);
  }

  return { allowed: true };
}
