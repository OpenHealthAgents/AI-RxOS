import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('./auth.js', () => {
  return {
    dbPool: {
      query: vi.fn(),
    },
  };
});

vi.mock('./rateLimit.js', () => {
  return {
    getRedisClient: vi.fn(async () => ({ set: vi.fn(async () => 'OK'), del: vi.fn(async () => 1) })),
  };
});

vi.mock('./audit.js', () => ({ recordAuditEvent: vi.fn(async () => {}) }));

const { scimSyncForOrganization } = await import('./scim.js');
const { dbPool } = await import('./auth.js');

describe('SCIM sync', () => {
  beforeEach(() => {
    (dbPool.query as any).mockReset();
  });

  it('returns organization_not_found when org missing', async () => {
    (dbPool.query as any).mockResolvedValueOnce({ rowCount: 0, rows: [] });
    const res = await scimSyncForOrganization('nonexistent');
    expect(res.ok).toBe(false);
    expect(res.message).toBe('organization_not_found');
  });

  it('upserts users from settings.scim.users', async () => {
    const orgRow = { id: 'org1', settings: { scim: { users: [{ userName: 'jdoe', emails: [{ value: 'jdoe@example.com' }], displayName: 'John Doe' }], enabled: true } } };
    // SELECT org
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [orgRow] })
      // SELECT existing members for org
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      // SELECT existing users by email -> none
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      // INSERT user
      .mockResolvedValueOnce({})
      // INSERT member
      .mockResolvedValueOnce({})
      // persist lastSyncAt update
      .mockResolvedValueOnce({});

    const res = await scimSyncForOrganization('org1');
    expect(res.ok).toBe(true);
    expect(res.summary.upserted).toBe(1);
    expect(res.summary.membersAdded).toBe(1);
  });

  it('applies groupRoleMap and updates member role', async () => {
    const orgRow = { id: 'org2', settings: { scim: { users: [{ userName: 'alice', emails: [{ value: 'alice@example.com' }], displayName: 'Alice', groups: ['admins'] }], enabled: true, groupRoleMap: { admins: 'admin' }, defaultRole: 'member' } } };
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [orgRow] })
      // SELECT existing users by email -> none
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      // INSERT user
      .mockResolvedValueOnce({})
      // SELECT member -> existing with role member
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ id: 'm1', role: 'member' }] })
      // UPDATE member role
      .mockResolvedValueOnce({})
      // persist lastSyncAt
      .mockResolvedValueOnce({});

    const res = await scimSyncForOrganization('org2');
    expect(res.ok).toBe(true);
    expect(res.summary.membersAdded).toBe(1);
  });

  it('fetches paginated results using next links', async () => {
    const orgRow = { id: 'org3', settings: { scim: { url: 'http://scim.example.com/Users', enabled: true } } };
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [orgRow] })
      // fetch users: existing users by email -> none
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      // insert user page1 (u1)
      .mockResolvedValueOnce({})
      // select member -> none (u1)
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      // insert member (u1)
      .mockResolvedValueOnce({})
      // insert user page2 (u2)
      .mockResolvedValueOnce({})
      // select member -> none (u2)
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      // insert member (u2)
      .mockResolvedValueOnce({})
      // persist lastSyncAt
      .mockResolvedValueOnce({});

    // mock global fetch to return two pages
    const page1 = {
      Resources: [{ userName: 'u1', emails: [{ value: 'u1@example.com' }], displayName: 'U1' }],
      links: [{ rel: 'next', href: 'http://scim.example.com/Users?page=2' }]
    };
    const page2 = {
      Resources: [{ userName: 'u2', emails: [{ value: 'u2@example.com' }], displayName: 'U2' }]
    };

    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => page1 })
      .mockResolvedValueOnce({ ok: true, json: async () => page2 });
    // @ts-ignore
    global.fetch = fetchMock;

    const res = await scimSyncForOrganization('org3');
    expect(res.ok).toBe(true);
    expect(res.summary.upserted).toBe(2);
    // cleanup
    // @ts-ignore
    delete global.fetch;
  });
});
