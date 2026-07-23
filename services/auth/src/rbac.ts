import { Request, Response, NextFunction } from "express";

export function hasRole(subjectRoles: string[] | undefined, required: string | string[]): boolean {
  if (!subjectRoles || subjectRoles.length === 0) return false;
  const reqRoles = Array.isArray(required) ? required : [required];
  return reqRoles.some((r) => subjectRoles.includes(r));
}

export function requireRole(required: string | string[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    // Roles may be provided via header `x-user-roles` as CSV or via body.subject.roles
    const header = (req.headers["x-user-roles"] as string) || "";
    const rolesFromHeader = header ? header.split(",").map((s) => s.trim()) : [];
    const bodyRoles = (req.body?.subject?.roles as string[]) ?? (req.body?.roles as string[]);
    const roles = [...rolesFromHeader, ...(bodyRoles ?? [])];

    if (!hasRole(roles, required)) {
      res.status(403).json({ code: "forbidden", message: "Insufficient role privileges" });
      return;
    }
    next();
  };
}

export default { hasRole, requireRole };
