import { describe, it, expect } from 'vitest';
import { resolveOidcProviderForEmail } from './oidc.js';

describe('OIDC enterprise discovery', () => {
  it('prefers the provider with the most specific domain match and highest priority', async () => {
    const providers = [
      { id: 'p1', name: 'Fallback', issuer: 'https://example.com', clientId: 'c1', enabled: true, domainHints: ['example.com'], priority: 10 },
      { id: 'p2', name: 'Finops', issuer: 'https://finops.example.com', clientId: 'c2', enabled: true, domainHints: ['finops.example.com'], priority: 100 },
      { id: 'p3', name: 'Admin', issuer: 'https://admin.example.com', clientId: 'c3', enabled: true, domainHints: ['admin.example.com'], priority: 90 },
    ];

    const result = await resolveOidcProviderForEmail('org1', 'user@finops.example.com', providers as any);
    expect(result?.id).toBe('p2');
  });

  it('returns the first enabled provider when no email-domain match exists', async () => {
    const providers = [
      { id: 'p1', name: 'Fallback', issuer: 'https://example.com', clientId: 'c1', enabled: true, priority: 10 },
      { id: 'p2', name: 'Secondary', issuer: 'https://secondary.example.com', clientId: 'c2', enabled: true, priority: 5 },
    ];

    const result = await resolveOidcProviderForEmail('org1', 'user@unknown.example', providers as any);
    expect(result?.id).toBe('p1');
  });
});
