import { describe, it, expect } from 'vitest';
import { evaluateABAC } from './abac.js';

describe('ABAC evaluator', () => {
  it('denies cross-tenant access', async () => {
    const res = await evaluateABAC({
      subject: { id: 'u1', roles: ['member'], clearanceLevel: 2, organizationId: 'org1' },
      resource: { sensitivityLevel: 1, organizationId: 'org2' },
      action: 'read'
    });
    expect(res.allowed).toBe(false);
  });

  it('allows owner with sufficient clearance', async () => {
    const res = await evaluateABAC({
      subject: { id: 'u1', roles: ['member'], clearanceLevel: 4, organizationId: 'org1' },
      resource: { sensitivityLevel: 3, organizationId: 'org1', ownerId: 'u1' },
      action: 'share'
    });
    expect(res.allowed).toBe(true);
  });
});
