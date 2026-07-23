import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import pg from 'pg';
import { initDatabase } from './db.js';
import { config } from './config.js';
import {
  createInvitation,
  acceptInvitation,
  rejectInvitation,
  resendInvitation,
  getInvitationById,
} from './invitations.js';

const pool = new pg.Pool({ connectionString: config.databaseUrl });
const orgId = '11111111-1111-1111-1111-111111111111';
const inviterId = '22222222-2222-2222-2222-222222222222';
const inviteeId = '33333333-3333-3333-3333-333333333333';
const inviteeEmail = 'invitee@example.com';

describe('Invitation lifecycle', () => {
  beforeAll(async () => {
    await initDatabase();
    await pool.query(`TRUNCATE TABLE member, invitation, organization, "user" RESTART IDENTITY CASCADE`);
    await pool.query(`INSERT INTO organization (id, name, slug, plan, max_users, max_workspaces, settings, created_at, updated_at)
      VALUES ($1, 'Test Org', 'test-org', 'free', 5, 3, '{}'::jsonb, NOW(), NOW())`, [orgId]);
    await pool.query(`INSERT INTO "user" (id, email, name, created_at, updated_at)
      VALUES ($1, 'inviter@example.com', 'Inviter', NOW(), NOW())`, [inviterId]);
    await pool.query(`INSERT INTO "user" (id, email, name, created_at, updated_at)
      VALUES ($1, $2, 'Invitee', NOW(), NOW())`, [inviteeId, inviteeEmail]);
  }, 20000);

  afterAll(async () => {
    await pool.end();
  });

  it('creates a pending invitation with expiration', async () => {
    const result = await createInvitation({
      organizationId: orgId,
      email: inviteeEmail,
      role: 'member',
      inviterId,
      ttlDays: 7,
    });

    expect(result.id).toBeTruthy();
    expect(result.status).toBe('pending');
    expect(result.expiresAt).toBeTruthy();
  });

  it('accepts a valid pending invitation and creates membership', async () => {
    const created = await createInvitation({
      organizationId: orgId,
      email: inviteeEmail,
      role: 'member',
      inviterId,
      ttlDays: 7,
    });

    const accepted = await acceptInvitation({
      invitationId: created.id,
      userEmail: inviteeEmail,
      userId: inviteeId,
    });

    expect(accepted.ok).toBe(true);

    const invitation = await getInvitationById(created.id);
    expect(invitation?.status).toBe('accepted');

    const memberRes = await pool.query(
      `SELECT id, organization_id, user_id, role FROM member WHERE organization_id = $1 AND user_id = $2`,
      [orgId, inviteeId]
    );
    expect(memberRes.rowCount).toBe(1);
  });

  it('rejects a pending invitation without changing membership', async () => {
    const created = await createInvitation({
      organizationId: orgId,
      email: 'reject@example.com',
      role: 'member',
      inviterId,
      ttlDays: 7,
    });

    const rejected = await rejectInvitation({
      invitationId: created.id,
      reason: 'declined',
      userId: inviterId,
    });

    expect(rejected.ok).toBe(true);
    const invitation = await getInvitationById(created.id);
    expect(invitation?.status).toBe('rejected');
  });

  it('resends a pending invitation by refreshing its expiration', async () => {
    const created = await createInvitation({
      organizationId: orgId,
      email: 'resend@example.com',
      role: 'admin',
      inviterId,
      ttlDays: 1,
    });

    const resent = await resendInvitation({ invitationId: created.id, ttlDays: 3, userId: inviterId });
    expect(resent.ok).toBe(true);

    const invitation = await getInvitationById(created.id);
    expect(invitation?.status).toBe('pending');
    expect(new Date(invitation!.expiresAt).getTime()).toBeGreaterThan(new Date(created.expiresAt).getTime());
  });

  it('returns an expired error for stale invitations', async () => {
    const created = await createInvitation({
      organizationId: orgId,
      email: 'expired@example.com',
      role: 'member',
      inviterId,
      ttlDays: 0,
    });

    await pool.query(`UPDATE invitation SET expires_at = NOW() - INTERVAL '1 minute' WHERE id = $1`, [created.id]);

    await expect(
      acceptInvitation({ invitationId: created.id, userEmail: 'expired@example.com', userId: inviteeId })
    ).rejects.toThrow('invite_expired');
  });
});
