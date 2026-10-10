import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./auth.js', () => ({ dbPool: { query: vi.fn() } }));
vi.mock('./rateLimit.js', () => ({ getRedisClient: vi.fn(async () => ({ set: vi.fn(async () => 'OK') })) }));
const { dbPool } = await import('./auth.js');

describe('Registration token lifecycle', () => {
  beforeEach(() => {
    (dbPool.query as any).mockReset();
  });

  it('rejects expired registration token', async () => {
    const now = Math.floor(Date.now() / 1000);
    const client = { client_id: 'c1', registration_access_token: 't', registration_access_token_expires_at: now - 10 };
    (dbPool.query as any).mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_dynamic_clients: [client] } }] });
    const oidc = await import('./oidc.js');
    const ok = await oidc.validateRegistrationAccessToken('org1', 'c1', 't');
    expect(ok).toBe(false);
  });

  it('revokes registration token', async () => {
    const client = { client_id: 'c1', registration_access_token: 't' };
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_dynamic_clients: [client] } }] })
      .mockResolvedValueOnce({});
    const oidc = await import('./oidc.js');
    await oidc.revokeRegistrationAccessToken('org1', 'c1');
    // update should have been called
    expect((dbPool.query as any).mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
