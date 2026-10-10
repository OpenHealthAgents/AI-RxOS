import crypto from 'crypto';
import { dbPool } from './auth.js';
import { recordAuditEvent } from './audit.js';

export type InvitationStatus = 'pending' | 'accepted' | 'rejected' | 'expired';

export interface CreateInvitationInput {
  organizationId: string;
  email: string;
  role?: string;
  inviterId: string;
  ttlDays?: number;
}

export interface AcceptInvitationInput {
  invitationId: string;
  userEmail: string;
  userId: string;
}

export interface RejectInvitationInput {
  invitationId: string;
  reason?: string;
  userId?: string;
}

export interface ResendInvitationInput {
  invitationId: string;
  ttlDays?: number;
  userId?: string;
}

export interface InvitationRecord {
  id: string;
  organizationId: string;
  email: string;
  role: string;
  status: InvitationStatus;
  expiresAt: string;
  inviterId: string | null;
  createdAt: string;
  updatedAt: string;
}

function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

function buildInvitationExpiration(ttlDays = 7) {
  const expiresAt = new Date(Date.now() + ttlDays * 24 * 60 * 60 * 1000);
  return expiresAt.toISOString();
}

function buildInviteEmailHtml({ organizationName, inviteeEmail, role, inviteLink, expiresAt }: { organizationName: string; inviteeEmail: string; role: string; inviteLink: string; expiresAt: string; }) {
  return `
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="margin-top:0;">Organization Invitation</h2>
      <p>You have been invited to join <strong>${organizationName}</strong> as <strong>${role}</strong>.</p>
      <p>Email: <strong>${inviteeEmail}</strong></p>
      <p>This invitation expires on <strong>${new Date(expiresAt).toUTCString()}</strong>.</p>
      <p>
        <a href="${inviteLink}" style="display:inline-block;background:#2563eb;color:#fff;padding:10px 16px;text-decoration:none;border-radius:8px;">Accept Invitation</a>
      </p>
      <p>If you did not expect this invitation, you can reject it from the auth portal.</p>
    </div>
  `;
}

function buildInviteEmailText({ organizationName, inviteeEmail, role, inviteLink, expiresAt }: { organizationName: string; inviteeEmail: string; role: string; inviteLink: string; expiresAt: string; }) {
  return [
    'Organization Invitation',
    '',
    `You have been invited to join ${organizationName} as ${role}.`,
    `Email: ${inviteeEmail}`,
    `This invitation expires on ${new Date(expiresAt).toUTCString()}.`,
    `Accept: ${inviteLink}`,
    'If you did not expect this invitation, you can reject it from the auth portal.',
  ].join('\n');
}

export async function createInvitation(input: CreateInvitationInput) {
  const email = normalizeEmail(input.email);
  const expiresAt = buildInvitationExpiration(input.ttlDays ?? 7);
  const inviteId = crypto.randomUUID();
  const organizationRes = await dbPool.query(`SELECT name FROM organization WHERE id = $1`, [input.organizationId]);
  if ((organizationRes.rowCount ?? 0) === 0) {
    throw new Error('organization_not_found');
  }

  const organizationName = organizationRes.rows[0].name as string;
  const inviteLink = `${process.env.PUBLIC_BASE_URL ?? 'http://localhost:3000'}/invite/accept?invitationId=${inviteId}`;

  await dbPool.query(
    `INSERT INTO invitation (id, organization_id, email, role, status, expires_at, inviter_id, created_at, updated_at)
     VALUES ($1, $2, $3, $4, 'pending', $5, $6, NOW(), NOW())`,
    [inviteId, input.organizationId, email, input.role ?? 'member', expiresAt, input.inviterId]
  );

  await recordAuditEvent({
    userId: input.inviterId,
    organizationId: input.organizationId,
    action: 'create_invitation',
    resourceType: 'invitation',
    resourceId: inviteId,
    metadata: {
      email,
      role: input.role ?? 'member',
      expiresAt,
    },
  });

  return {
    id: inviteId,
    organizationId: input.organizationId,
    email,
    role: input.role ?? 'member',
    status: 'pending' as const,
    expiresAt,
    inviterId: input.inviterId,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    emailTemplate: {
      subject: `Invitation to join ${organizationName}`,
      html: buildInviteEmailHtml({ organizationName, inviteeEmail: email, role: input.role ?? 'member', inviteLink, expiresAt }),
      text: buildInviteEmailText({ organizationName, inviteeEmail: email, role: input.role ?? 'member', inviteLink, expiresAt }),
    },
  };
}

export async function getInvitationById(invitationId: string): Promise<InvitationRecord | null> {
  const res = await dbPool.query(
    `SELECT id, organization_id, email, role, status, expires_at, inviter_id, created_at, updated_at
     FROM invitation WHERE id = $1`,
    [invitationId]
  );
  if ((res.rowCount ?? 0) === 0) {
    return null;
  }
  const row = res.rows[0];
  return {
    id: row.id,
    organizationId: row.organization_id,
    email: row.email,
    role: row.role,
    status: row.status,
    expiresAt: row.expires_at,
    inviterId: row.inviter_id,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export async function acceptInvitation(input: AcceptInvitationInput) {
  const invitation = await getInvitationById(input.invitationId);
  if (!invitation) {
    throw new Error('invite_not_found');
  }
  if (invitation.status !== 'pending') {
    throw new Error('invite_invalid');
  }
  if (new Date(invitation.expiresAt).getTime() < Date.now()) {
    await dbPool.query(`UPDATE invitation SET status = 'expired', updated_at = NOW() WHERE id = $1`, [input.invitationId]);
    throw new Error('invite_expired');
  }

  let userId = input.userId;
  let userEmail = normalizeEmail(input.userEmail);

  const userRes = await dbPool.query(
    `SELECT id, email FROM "user" WHERE id = $1 OR email = $2 ORDER BY CASE WHEN id = $1 THEN 0 ELSE 1 END LIMIT 1`,
    [input.userId, userEmail]
  );

  if ((userRes.rowCount ?? 0) === 0) {
    throw new Error('user_not_found');
  }

  userId = userRes.rows[0].id as string;
  userEmail = normalizeEmail(userRes.rows[0].email as string);

  if (normalizeEmail(invitation.email) !== userEmail) {
    throw new Error('invite_mismatch');
  }

  await dbPool.query(
    `INSERT INTO member (id, organization_id, user_id, role, created_at, updated_at)
     VALUES ($1, $2, $3, $4, NOW(), NOW())
     ON CONFLICT (organization_id, user_id) DO UPDATE SET role = EXCLUDED.role, updated_at = NOW()`,
    [crypto.randomUUID(), invitation.organizationId, userId, invitation.role]
  );

  await dbPool.query(`UPDATE invitation SET status = 'accepted', updated_at = NOW() WHERE id = $1`, [input.invitationId]);

  await recordAuditEvent({
    userId,
    organizationId: invitation.organizationId,
    action: 'accept_invitation',
    resourceType: 'invitation',
    resourceId: invitation.id,
    metadata: {
      email: invitation.email,
      role: invitation.role,
    },
  });

  return { ok: true };
}

export async function rejectInvitation(input: RejectInvitationInput) {
  const invitation = await getInvitationById(input.invitationId);
  if (!invitation) {
    throw new Error('invite_not_found');
  }
  if (invitation.status !== 'pending') {
    throw new Error('invite_invalid');
  }

  await dbPool.query(`UPDATE invitation SET status = 'rejected', updated_at = NOW() WHERE id = $1`, [input.invitationId]);

  await recordAuditEvent({
    userId: input.userId ?? null,
    organizationId: invitation.organizationId,
    action: 'reject_invitation',
    resourceType: 'invitation',
    resourceId: invitation.id,
    metadata: {
      reason: input.reason ?? 'rejected',
      email: invitation.email,
    },
  });

  return { ok: true };
}

export async function resendInvitation(input: ResendInvitationInput) {
  const invitation = await getInvitationById(input.invitationId);
  if (!invitation) {
    throw new Error('invite_not_found');
  }
  if (invitation.status !== 'pending') {
    throw new Error('invite_invalid');
  }
  if (new Date(invitation.expiresAt).getTime() < Date.now()) {
    await dbPool.query(`UPDATE invitation SET status = 'expired', updated_at = NOW() WHERE id = $1`, [input.invitationId]);
    throw new Error('invite_expired');
  }

  const expiresAt = buildInvitationExpiration(input.ttlDays ?? 7);
  await dbPool.query(`UPDATE invitation SET expires_at = $2, updated_at = NOW() WHERE id = $1`, [input.invitationId, expiresAt]);

  await recordAuditEvent({
    userId: input.userId ?? null,
    organizationId: invitation.organizationId,
    action: 'resend_invitation',
    resourceType: 'invitation',
    resourceId: invitation.id,
    metadata: {
      email: invitation.email,
      expiresAt,
    },
  });

  return {
    ok: true,
    expiresAt,
  };
}
