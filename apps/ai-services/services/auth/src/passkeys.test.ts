import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('./auth.js', () => ({ dbPool: { query: vi.fn() } }));
const { dbPool } = await import('./auth.js');
const { listPasskeysForUser, renamePasskey, revokePasskey, getPasskeyDevice, listPasskeysForOrganization } = await import('./passkeys.js');

describe('Passkeys helper', () => {
  beforeEach(() => {
    (dbPool.query as any).mockReset();
  });

  it('lists passkeys for a user', async () => {
    (dbPool.query as any).mockResolvedValueOnce({ rows: [{ id: 'd1', accountId: 'a1', providerId: 'passkey-web', accountIdentifier: 'acct1', name: 'Chrome Key', lastUsedAt: null, revokedAt: null, createdAt: new Date().toISOString() }] });
    const res = await listPasskeysForUser('user1');
    expect(res).toHaveLength(1);
    expect(res[0]?.name).toBe('Chrome Key');
  });

  it('renames a passkey for the owner', async () => {
    (dbPool.query as any).mockResolvedValueOnce({ rowCount: 1 });
    const ok = await renamePasskey('d1', 'user1', 'New Name');
    expect(ok).toBe(true);
  });

  it('revokes a passkey as admin', async () => {
    (dbPool.query as any).mockResolvedValueOnce({ rowCount: 1 });
    const ok = await revokePasskey('d1', null, true);
    expect(ok).toBe(true);
  });

  it('gets a passkey device', async () => {
    (dbPool.query as any).mockResolvedValueOnce({ rowCount:1, rows: [{ id: 'd1', accountId: 'a1', providerId: 'passkey-web', accountIdentifier: 'acct1', name: 'Chrome Key' }] });
    const d = await getPasskeyDevice('d1');
    expect(d).not.toBeNull();
    expect(d?.id).toBe('d1');
  });

  it('lists passkeys for organization', async () => {
    (dbPool.query as any).mockResolvedValueOnce({ rows: [{ id: 'd1', accountId: 'a1', providerId: 'passkey-web', accountIdentifier: 'acct1', name: 'Chrome Key' }] });
    const r = await listPasskeysForOrganization('org1');
    expect(r).toHaveLength(1);
  });
});
