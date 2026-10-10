import { dbPool } from './auth.js';
import crypto from 'crypto';
import { authenticator } from 'otplib';
import jwt from 'jsonwebtoken';
import QRCode from 'qrcode';
import { config } from './config.js';
import { recordAuditEvent } from './audit.js';

export function generateBackupCodes(count = 10) {
  const codes: string[] = [];
  for (let i = 0; i < count; i++) {
    const code = crypto.randomBytes(4).toString('hex');
    codes.push(code.toUpperCase());
  }
  return codes;
}

export function hashCode(code: string) {
  return crypto.createHash('sha256').update(code, 'utf8').digest('hex');
}

export async function enableTotpForUser(userId: string) {
  const secret = authenticator.generateSecret();
  const backupCodes = generateBackupCodes(10);
  const hashed = backupCodes.map((c) => hashCode(c));

  await dbPool.query(
    `INSERT INTO mfa (user_id, totp_secret, backup_codes, recovery_codes, enabled)
     VALUES ($1, $2, $3::jsonb, $4::jsonb, true)
     ON CONFLICT (user_id) DO UPDATE SET totp_secret = EXCLUDED.totp_secret, backup_codes = EXCLUDED.backup_codes, enabled = true`,
    [userId, secret, JSON.stringify(hashed), JSON.stringify([])]
  );

  await recordAuditEvent({ userId, organizationId: null, action: 'mfa_enable', resourceType: 'mfa', resourceId: userId, metadata: { method: 'totp' } });

  return { secret, backupCodes };
}

export async function disableMfaForUser(userId: string) {
  await dbPool.query(`UPDATE mfa SET enabled = false WHERE user_id = $1`, [userId]);
  await recordAuditEvent({ userId, organizationId: null, action: 'mfa_disable', resourceType: 'mfa', resourceId: userId, metadata: {} });
}

export async function getTotpQr(userId: string, appName = 'AI-RxOS') {
  const res = await dbPool.query(`SELECT totp_secret FROM mfa WHERE user_id = $1`, [userId]);
  if (res.rowCount === 0 || !res.rows[0].totp_secret) throw new Error('TOTP not enabled');
  const secret = res.rows[0].totp_secret as string;
  const otpauth = authenticator.keyuri(userId, appName, secret);
  const dataUrl = await QRCode.toDataURL(otpauth);
  return { dataUrl, secret };
}

export async function verifyTotp(userId: string, token: string) {
  const res = await dbPool.query(`SELECT totp_secret, enabled FROM mfa WHERE user_id = $1`, [userId]);
  if (res.rowCount === 0) return false;
  const row = res.rows[0];
  if (!row.enabled || !row.totp_secret) return false;
  const secret = row.totp_secret as string;
  return authenticator.check(token, secret);
}

export function createMfaLoginChallenge(userId: string, organizationId: string, roles: string[]) {
  return jwt.sign(
    {
      sub: userId,
      organizationId,
      roles,
      purpose: 'mfa_login',
    },
    config.jwtSecret,
    { expiresIn: '5m' }
  );
}

export function verifyMfaLoginChallenge(challengeToken: string) {
  try {
    const decoded = jwt.verify(challengeToken, config.jwtSecret) as Record<string, unknown>;
    if (
      decoded &&
      typeof decoded === 'object' &&
      decoded.purpose === 'mfa_login' &&
      typeof decoded.sub === 'string' &&
      typeof decoded.organizationId === 'string' &&
      Array.isArray(decoded.roles)
    ) {
      return {
        userId: decoded.sub,
        organizationId: decoded.organizationId,
        roles: decoded.roles.filter((item) => typeof item === 'string').map(String),
      };
    }
  } catch {
    return null;
  }
  return null;
}

export async function consumeBackupCode(userId: string, code: string) {
  const res = await dbPool.query(`SELECT backup_codes FROM mfa WHERE user_id = $1`, [userId]);
  if (res.rowCount === 0) return false;
  const hashes: string[] = res.rows[0].backup_codes ?? [];
  const h = hashCode(code);
  const idx = hashes.indexOf(h);
  if (idx === -1) return false;
  hashes.splice(idx, 1);
  await dbPool.query(`UPDATE mfa SET backup_codes = $2 WHERE user_id = $1`, [userId, JSON.stringify(hashes)]);
  await recordAuditEvent({ userId, organizationId: null, action: 'mfa_backup_code_used', resourceType: 'mfa', resourceId: userId, metadata: {} });
  return true;
}

export async function regenBackupCodes(userId: string) {
  const codes = generateBackupCodes(10);
  const hashed = codes.map((c) => hashCode(c));
  await dbPool.query(`UPDATE mfa SET backup_codes = $2 WHERE user_id = $1`, [userId, JSON.stringify(hashed)]);
  await recordAuditEvent({ userId, organizationId: null, action: 'mfa_backup_codes_regenerated', resourceType: 'mfa', resourceId: userId, metadata: {} });
  return codes;
}

export async function getUserMfaEnabled(userId: string) {
  const res = await dbPool.query(`SELECT enabled FROM mfa WHERE user_id = $1`, [userId]);
  return (res.rowCount ?? 0) > 0 && res.rows[0].enabled === true;
}

export function generateRecoveryCodes(count = 5) {
  const codes: string[] = [];
  for (let i = 0; i < count; i++) {
    const code = crypto.randomBytes(6).toString('hex');
    codes.push(code.toUpperCase());
  }
  return codes;
}

export async function regenRecoveryCodes(userId: string) {
  const codes = generateRecoveryCodes(5);
  const hashed = codes.map((c) => hashCode(c));
  await dbPool.query(`UPDATE mfa SET recovery_codes = $2 WHERE user_id = $1`, [userId, JSON.stringify(hashed)]);
  await recordAuditEvent({ userId, organizationId: null, action: 'mfa_recovery_codes_regenerated', resourceType: 'mfa', resourceId: userId, metadata: {} });
  return codes;
}

export async function consumeRecoveryCode(userId: string, code: string) {
  const res = await dbPool.query(`SELECT recovery_codes FROM mfa WHERE user_id = $1`, [userId]);
  if (res.rowCount === 0) return false;
  const hashes: string[] = res.rows[0].recovery_codes ?? [];
  const h = hashCode(code);
  const idx = hashes.indexOf(h);
  if (idx === -1) return false;
  hashes.splice(idx, 1);
  await dbPool.query(`UPDATE mfa SET recovery_codes = $2 WHERE user_id = $1`, [userId, JSON.stringify(hashes)]);
  await recordAuditEvent({ userId, organizationId: null, action: 'mfa_recovery_code_used', resourceType: 'mfa', resourceId: userId, metadata: {} });
  return true;
}

export async function getMfaStatus(userId: string) {
  const res = await dbPool.query(`SELECT totp_secret IS NOT NULL AS totp_enabled, COALESCE(jsonb_array_length(backup_codes), 0) AS backup_count, COALESCE(jsonb_array_length(recovery_codes), 0) AS recovery_count, enabled FROM mfa WHERE user_id = $1`, [userId]);
  if (res.rowCount === 0) return { enabled: false, totp: false, backupCount: 0, recoveryCount: 0 };
  const row = res.rows[0];
  return { enabled: !!row.enabled, totp: !!row.totp_enabled, backupCount: row.backup_count ?? 0, recoveryCount: row.recovery_count ?? 0 };
}
