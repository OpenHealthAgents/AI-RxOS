import { AsyncLocalStorage } from 'async_hooks';
import jwt from 'jsonwebtoken';
import type { Request, Response, NextFunction } from 'express';
import { config } from './config.js';

type AuthPayload = {
  userId: string;
  organizationId: string;
  roles: string[];
};

type TenantStore = {
  organizationId: string | null;
  auth: AuthPayload | null;
};

const tenantStore = new AsyncLocalStorage<TenantStore>();

export function getCurrentTenantOrganizationId(): string | null {
  return tenantStore.getStore()?.organizationId ?? null;
}

export function getCurrentAuthPayload(): AuthPayload | null {
  return tenantStore.getStore()?.auth ?? null;
}

export function runWithTenantOrganizationId<T>(organizationId: string | null, fn: () => Promise<T>): Promise<T> {
  return tenantStore.run({ organizationId, auth: null }, fn);
}

function parseBearerToken(authorizationHeader: string | undefined): string | null {
  if (!authorizationHeader) return null;
  const match = authorizationHeader.match(/^Bearer\s+(.+)$/i);
  return match?.[1] ?? null;
}

function verifyLegacyAccessToken(token: string): AuthPayload | null {
  try {
    const decoded = jwt.verify(token, config.jwtSecret) as Record<string, unknown>;
    if (
      decoded &&
      typeof decoded === 'object' &&
      typeof decoded.sub === 'string' &&
      typeof decoded.organizationId === 'string'
    ) {
      const roles = Array.isArray(decoded.roles)
        ? decoded.roles.filter((item) => typeof item === 'string').map((item) => String(item))
        : [];
      return {
        userId: decoded.sub,
        organizationId: decoded.organizationId,
        roles,
      };
    }
  } catch {
    // invalid token is intentionally ignored here; request remains unauthenticated
  }
  return null;
}

export function tenantContextMiddleware(req: Request, _res: Response, next: NextFunction) {
  const token = parseBearerToken(req.headers.authorization as string | undefined);
  const authPayload = token ? verifyLegacyAccessToken(token) : null;
  const organizationId = authPayload?.organizationId ?? null;

  if (authPayload) {
    (req as any).auth = authPayload;
    (req as any).user = {
      id: authPayload.userId,
      roles: authPayload.roles,
      organizationId: authPayload.organizationId,
    };
  }

  tenantStore.run({ organizationId, auth: authPayload }, () => next());
}
