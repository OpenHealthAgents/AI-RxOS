import type { Request, Response, NextFunction } from "express";

export type ApplicationRole =
  | "admin"
  | "scientist"
  | "clinical_researcher"
  | "bd"
  | "licensing"
  | "executive"
  | "analyst"
  | "reviewer";

export type ApplicationPermission =
  | "tenant:admin"
  | "canonical:read"
  | "canonical:write"
  | "evidence:read"
  | "evidence:review"
  | "clinical:read"
  | "clinical:write"
  | "commercial:read"
  | "licensing:read"
  | "recommendation:read"
  | "recommendation:write"
  | "report:read"
  | "report:export"
  | "search:read";

const ROLE_ALIASES: Readonly<Record<string, ApplicationRole>> = {
  administrator: "admin",
  owner: "admin",
  "clinical researcher": "clinical_researcher",
  clinical_researcher: "clinical_researcher",
  business_development: "bd",
  "business development": "bd",
};

export const ROLE_PERMISSIONS: Readonly<Record<ApplicationRole, ReadonlySet<ApplicationPermission>>> = {
  admin: new Set<ApplicationPermission>([
    "tenant:admin",
    "canonical:read",
    "canonical:write",
    "evidence:read",
    "evidence:review",
    "clinical:read",
    "clinical:write",
    "commercial:read",
    "licensing:read",
    "recommendation:read",
    "recommendation:write",
    "report:read",
    "report:export",
    "search:read",
  ]),
  scientist: new Set(["canonical:read", "canonical:write", "evidence:read", "recommendation:read", "recommendation:write", "report:read", "search:read"]),
  clinical_researcher: new Set(["canonical:read", "evidence:read", "clinical:read", "clinical:write", "recommendation:read", "report:read", "search:read"]),
  bd: new Set(["canonical:read", "commercial:read", "recommendation:read", "report:read", "report:export", "search:read"]),
  licensing: new Set(["canonical:read", "commercial:read", "licensing:read", "report:read", "report:export", "search:read"]),
  executive: new Set(["canonical:read", "commercial:read", "recommendation:read", "report:read", "report:export", "search:read"]),
  analyst: new Set(["canonical:read", "evidence:read", "recommendation:read", "report:read", "report:export", "search:read"]),
  reviewer: new Set(["canonical:read", "evidence:read", "evidence:review", "recommendation:read", "report:read", "search:read"]),
};

export function normalizeRole(role: string): ApplicationRole | null {
  const normalized = role.trim().toLowerCase().replace(/[-_]+/g, " ");
  const alias = ROLE_ALIASES[normalized] ?? ROLE_ALIASES[normalized.replace(/ /g, "_")];
  if (alias) return alias;
  return (Object.keys(ROLE_PERMISSIONS) as ApplicationRole[]).find(
    (candidate) => candidate.replace(/_/g, " ") === normalized,
  ) ?? null;
}

export function hasRole(subjectRoles: string[] | undefined, required: string | string[]): boolean {
  if (!subjectRoles?.length) return false;
  const roles = new Set(subjectRoles.map(normalizeRole).filter((role): role is ApplicationRole => role !== null));
  const requested = (Array.isArray(required) ? required : [required])
    .map(normalizeRole)
    .filter((role): role is ApplicationRole => role !== null);
  return requested.some((role) => roles.has(role));
}

export function hasPermission(subjectRoles: string[] | undefined, required: ApplicationPermission): boolean {
  return (subjectRoles ?? []).some((role) => {
    const normalized = normalizeRole(role);
    return normalized !== null && ROLE_PERMISSIONS[normalized].has(required);
  });
}

type AuthenticatedRequest = Request & {
  auth?: { userId: string; organizationId: string; roles: string[] };
};

function requestedOrganization(req: Request): unknown {
  return req.params?.organizationId ?? req.query?.organizationId ?? req.body?.organizationId;
}

function authorize(
  req: AuthenticatedRequest,
  res: Response,
  next: NextFunction,
  allowed: (roles: string[]) => boolean,
): void {
  const principal = req.auth;
  if (!principal?.userId) {
    res.status(401).json({ code: "unauthorized", message: "Authentication required" });
    return;
  }
  if (!principal.organizationId) {
    res.status(403).json({ code: "tenant_context_required", message: "Authenticated tenant context is required" });
    return;
  }
  const targetOrganization = requestedOrganization(req);
  if (
    targetOrganization !== undefined &&
    targetOrganization !== null &&
    String(targetOrganization) !== principal.organizationId
  ) {
    res.status(403).json({ code: "forbidden", message: "Cross-tenant access is not allowed" });
    return;
  }
  if (!allowed(principal.roles)) {
    res.status(403).json({ code: "forbidden", message: "Insufficient role privileges" });
    return;
  }
  next();
}

export function requireRole(required: string | string[]) {
  return (req: Request, res: Response, next: NextFunction) =>
    authorize(req as AuthenticatedRequest, res, next, (roles) => hasRole(roles, required));
}

export function requirePermission(required: ApplicationPermission) {
  return (req: Request, res: Response, next: NextFunction) =>
    authorize(req as AuthenticatedRequest, res, next, (roles) => hasPermission(roles, required));
}

export default { hasRole, hasPermission, requireRole, requirePermission };
