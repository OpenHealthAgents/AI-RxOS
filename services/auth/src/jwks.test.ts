import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./rateLimit.js', () => ({ getRedisClient: vi.fn(async () => null) }));

const jwksBody = { keys: [{ kid: 'k1' }, { kid: 'k2' }] };

describe('JWKS cache', () => {
  beforeEach(() => {
    delete (globalThis as any).fetch;
  });

  it('fetches and caches jwks on miss', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => jwksBody });
    (globalThis as any).fetch = fetchMock;
    const jwks = await (await import('./jwksCache.js')).getJwks('https://example.com/jwks');
    expect(jwks.keys.length).toBe(2);
    // second time should hit memory cache and not call fetch
    const jwks2 = await (await import('./jwksCache.js')).getJwks('https://example.com/jwks');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(jwks2.keys.length).toBe(2);
  }, { timeout: 20000 });

  it('forceRefreshJwks updates the cache', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => jwksBody })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ keys: [{ kid: 'new' }] }) });
    (globalThis as any).fetch = fetchMock;
    const mod = await import('./jwksCache.js');
    const first = await mod.getJwks('https://example.com/jwks2');
    expect(first.keys[0].kid).toBe('k1');
    const refreshed = await mod.forceRefreshJwks('https://example.com/jwks2');
    expect(refreshed.keys[0].kid).toBe('new');
  }, { timeout: 20000 });
});
