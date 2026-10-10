import { describe, it, expect, vi } from 'vitest';
import { hasPermission, hasRole, requirePermission, requireRole } from './rbac.js';

function middlewareResponse() {
  const response = {
    statusCode: 200,
    body: undefined as unknown,
    status(code: number) {
      this.statusCode = code;
      return this;
    },
    json(body: unknown) {
      this.body = body;
      return this;
    },
  };
  const next = vi.fn();
  return { response, next };
}

describe('RBAC policy', () => {
  it.each([
    ['Admin', 'tenant:admin', true],
    ['Scientist', 'recommendation:write', true],
    ['Clinical Researcher', 'clinical:write', true],
    ['BD', 'commercial:read', true],
    ['Licensing', 'licensing:read', true],
    ['Executive', 'report:export', true],
    ['Analyst', 'evidence:review', false],
    ['Reviewer', 'evidence:review', true],
  ])('%s role has the expected %s permission', (role, permission, expected) => {
    expect(hasPermission([role], permission as never)).toBe(expected);
  });

  it('preserves owner/admin aliases without granting admin to other roles', () => {
    expect(hasRole(['owner'], 'admin')).toBe(true);
    expect(hasRole(['member'], ['owner', 'admin'])).toBe(false);
    expect(hasPermission(['Scientist'], 'tenant:admin')).toBe(false);
  });

  it('ignores caller-supplied roles and requires authenticated tenant context', () => {
    const middleware = requireRole('admin');
    const { response, next } = middlewareResponse();
    middleware(
      {
        headers: { 'x-user-roles': 'admin' },
        body: { roles: ['admin'] },
        auth: undefined,
      } as never,
      response as never,
      next,
    );
    expect(response.statusCode).toBe(401);
    expect(next).not.toHaveBeenCalled();
  });

  it('rejects missing tenant and forged cross-tenant organization targets', () => {
    const middleware = requireRole('admin');
    const missingTenant = middlewareResponse();
    middleware({ auth: { userId: 'u1', organizationId: '', roles: ['admin'] } } as never, missingTenant.response as never, missingTenant.next);
    expect(missingTenant.response.statusCode).toBe(403);

    const crossTenant = middlewareResponse();
    middleware(
      {
        auth: { userId: 'u1', organizationId: 'tenant-a', roles: ['admin'] },
        body: { organizationId: 'tenant-b' },
      } as never,
      crossTenant.response as never,
      crossTenant.next,
    );
    expect(crossTenant.response.statusCode).toBe(403);
    expect(crossTenant.next).not.toHaveBeenCalled();
  });

  it('allows an authorized, tenant-matching principal', () => {
    const middleware = requirePermission('evidence:review');
    const { response, next } = middlewareResponse();
    middleware(
      {
        auth: { userId: 'reviewer-1', organizationId: 'tenant-a', roles: ['reviewer'] },
        query: { organizationId: 'tenant-a' },
      } as never,
      response as never,
      next,
    );
    expect(response.statusCode).toBe(200);
    expect(next).toHaveBeenCalledOnce();
  });
});
