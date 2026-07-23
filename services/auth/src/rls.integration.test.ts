import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import pg from 'pg';
import { initDatabase } from './db.js';
import { config } from './config.js';

const pool = new pg.Pool({ connectionString: config.databaseUrl });
let appPool: pg.Pool | null = null;

async function withTenant<T>(organizationId: string | null, callback: (client: pg.PoolClient) => Promise<T>): Promise<T> {
  const client = await (appPool ?? pool).connect();
  try {
    if (organizationId) {
      // Use set_config to set the session GUC with a parameterized value
      await client.query("SELECT set_config('app.organization_id', $1, false)", [organizationId]);
    }
    // Debug: verify the setting is visible to this session and the helper
    const settingRes = await client.query("SELECT current_setting('app.organization_id', true) AS setting, app_current_tenant() AS tenant, current_user, session_user, (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user) AS rolbypassrls");
    console.log('withTenant: session setting and tenant ->', settingRes.rows[0]);
    return callback(client);
  } finally {
    try {
      await client.query('RESET app.organization_id');
    } catch (e) {
      // ignore
    }
    client.release();
  }
}

describe('Postgres RLS tenant isolation', () => {
  const orgA = '11111111-1111-1111-1111-111111111111';
  const orgB = '22222222-2222-2222-2222-222222222222';
  const userA = '33333333-3333-3333-3333-333333333333';
  const userB = '44444444-4444-4444-4444-444444444444';
  const accountA = '55555555-5555-5555-5555-555555555555';
  const accountB = '66666666-6666-6666-6666-666666666666';
  const passkeyA = '77777777-7777-7777-7777-777777777777';
  const passkeyB = '88888888-8888-8888-8888-888888888888';
  const sessionA = '99999999-9999-9999-9999-999999999999';
  const sessionB = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  const invitationA = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  const invitationB = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
  const memberA = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  const memberB = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  const auditA = 'dddddddd-dddd-dddd-dddd-dddddddddddd';
  const auditB = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';

  beforeAll(async () => {
    await initDatabase();
    // Create a non-superuser role for application-level connections used in tests
    await pool.query(
      `DO $$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_rxos_app') THEN
          CREATE ROLE ai_rxos_app LOGIN PASSWORD 'changeme_app';
        ELSE
          ALTER ROLE ai_rxos_app WITH LOGIN PASSWORD 'changeme_app';
        END IF;
        -- Ensure the app role does not bypass RLS
        ALTER ROLE ai_rxos_app NOBYPASSRLS;
      END$$;
    `
    );

    // Grant basic privileges to the app role so it can access schema objects
    await pool.query(`GRANT CONNECT ON DATABASE ai_rxos TO ai_rxos_app`);
    await pool.query(`GRANT USAGE ON SCHEMA public TO ai_rxos_app`);
    await pool.query(`GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_rxos_app`);
    await pool.query(`ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ai_rxos_app`);

    // Create an appPool that connects as the non-superuser
    const hostAndRest = config.databaseUrl.includes('@') ? config.databaseUrl.split('@')[1] : config.databaseUrl;
    const appConn = `postgresql://ai_rxos_app:changeme_app@${hostAndRest}`;
    appPool = new pg.Pool({ connectionString: appConn });

    // Use admin (superuser) connection to seed initial data; superuser bypasses RLS so
    // we can insert all rows without session GUC gymnastics.
    const adminClient = await pool.connect();
    try {
      await adminClient.query("SELECT set_config('audit.log_hmac_secret', $1, true)", [process.env.AUDIT_LOG_HMAC_SECRET || 'test-audit-log-secret']);

      await adminClient.query(
        `INSERT INTO "user" (id, email, name, created_at, updated_at)
         VALUES ($1, $2, $3, NOW(), NOW()), ($4, $5, $6, NOW(), NOW()) ON CONFLICT DO NOTHING`,
        [userA, 'a@example.com', 'User A', userB, 'b@example.com', 'User B']
      );

      await adminClient.query(
        `INSERT INTO organization (id, name, slug, created_at, updated_at)
         VALUES ($1, $2, $3, NOW(), NOW()), ($4, $5, $6, NOW(), NOW()) ON CONFLICT DO NOTHING`,
        [orgA, 'Org A', 'org-a', orgB, 'Org B', 'org-b']
      );

      await adminClient.query(
        `INSERT INTO member (id, organization_id, user_id, role, created_at, updated_at)
         VALUES ($1, $2, $3, 'owner', NOW(), NOW()), ($4, $5, $6, 'owner', NOW(), NOW()) ON CONFLICT DO NOTHING`,
        [memberA, orgA, userA, memberB, orgB, userB]
      );

      await adminClient.query(
        `INSERT INTO account (id, account_id, provider_id, user_id, created_at, updated_at)
         VALUES ($1, $2, $3, $4, NOW(), NOW()), ($5, $6, $7, $8, NOW(), NOW()) ON CONFLICT DO NOTHING`,
        [accountA, 'acct-a', 'passkey-web', userA, accountB, 'acct-b', 'passkey-web', userB]
      );

      await adminClient.query(
        `INSERT INTO passkey_device (id, account_id, name, created_at, updated_at)
         VALUES ($1, $2, 'A Key', NOW(), NOW()), ($3, $4, 'B Key', NOW(), NOW()) ON CONFLICT DO NOTHING`,
        [passkeyA, accountA, passkeyB, accountB]
      );

      await adminClient.query(
        `INSERT INTO session (id, user_id, token, expires_at, created_at, updated_at)
         VALUES ($1, $2, $3, NOW() + INTERVAL '1 day', NOW(), NOW()), ($4, $5, $6, NOW() + INTERVAL '1 day', NOW(), NOW()) ON CONFLICT DO NOTHING`,
        [sessionA, userA, 'token-a', sessionB, userB, 'token-b']
      );

      await adminClient.query(
        `INSERT INTO invitation (id, organization_id, email, role, status, expires_at, inviter_id, created_at, updated_at)
         VALUES ($1, $2, $3, 'member', 'pending', NOW() + INTERVAL '7 day', $4, NOW(), NOW()),
                ($5, $6, $7, 'member', 'pending', NOW() + INTERVAL '7 day', $8, NOW(), NOW()) ON CONFLICT DO NOTHING`,
        [invitationA, orgA, 'invite-a@example.com', userA, invitationB, orgB, 'invite-b@example.com', userB]
      );

      await adminClient.query(
        `INSERT INTO audit_log (id, user_id, organization_id, action, resource_type, created_at)
         VALUES ($1, $2, $3, 'create', 'test', NOW()), ($4, $5, $6, 'create', 'test', NOW()) ON CONFLICT DO NOTHING`,
        [auditA, userA, orgA, auditB, userB, orgB]
      );
    } finally {
      adminClient.release();
    }
  });

  afterAll(async () => {
    if (appPool) await appPool.end();
    await pool.end();
  });

  it('allows org A to read its own user and denies org B user', async () => {
    const rowA = await withTenant(orgA, (client) => client.query('SELECT id FROM "user" WHERE id = $1', [userA]));
    expect(rowA.rowCount).toBe(1);

    const rowB = await withTenant(orgA, (client) => client.query('SELECT id FROM "user" WHERE id = $1', [userB]));
    expect(rowB.rowCount).toBe(0);
  });

  it('denies org B from reading org A passkey devices', async () => {
    const rows = await withTenant(orgB, (client) => client.query('SELECT id FROM passkey_device WHERE id = $1', [passkeyA]));
    expect(rows.rowCount).toBe(0);
  });

  it('denies org A from reading org B sessions', async () => {
    const rows = await withTenant(orgA, (client) => client.query('SELECT id FROM session WHERE id = $1', [sessionB]));
    expect(rows.rowCount).toBe(0);
  });

  it('denies org B from reading org A invitations', async () => {
    const rows = await withTenant(orgB, (client) => client.query('SELECT id FROM invitation WHERE id = $1', [invitationA]));
    expect(rows.rowCount).toBe(0);
  });

  it('denies org A from reading org B audit log entries', async () => {
    const rows = await withTenant(orgA, (client) => client.query('SELECT id FROM audit_log WHERE id = $1', [auditB]));
    expect(rows.rowCount).toBe(0);
  });

  it('allows org B to read its own organization row and denies org A row', async () => {
    const rowB = await withTenant(orgB, (client) => client.query('SELECT id FROM organization WHERE id = $1', [orgB]));
    expect(rowB.rowCount).toBe(1);

    const rowA = await withTenant(orgB, (client) => client.query('SELECT id FROM organization WHERE id = $1', [orgA]));
    expect(rowA.rowCount).toBe(0);
  });

  it('prevents org A from deleting org B session row through RLS', async () => {
    const result = await withTenant(orgA, (client) => client.query('DELETE FROM session WHERE id = $1 RETURNING id', [sessionB]));
    expect(result.rowCount).toBe(0);

    const verify = await pool.query('SELECT id FROM session WHERE id = $1', [sessionB]);
    expect(verify.rowCount).toBe(1);
  });
});
