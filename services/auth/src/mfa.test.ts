import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import pg from 'pg';
import { initDatabase } from './db.js';
import { config } from './config.js';
import {
  enableTotpForUser,
  verifyTotp,
  regenBackupCodes,
  consumeBackupCode,
  regenRecoveryCodes,
  consumeRecoveryCode,
  getMfaStatus,
  disableMfaForUser,
  getUserMfaEnabled,
  createMfaLoginChallenge,
  verifyMfaLoginChallenge,
} from './mfa.js';
import { authenticator } from 'otplib';

const pool = new pg.Pool({ connectionString: config.databaseUrl });
const testUser = 'aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa';

describe('MFA module', () => {
  beforeAll(async () => {
    await initDatabase();
    // Ensure test user exists (no transaction so other connections can see it)
    await pool.query(`INSERT INTO "user" (id, email, name, created_at, updated_at) VALUES ($1,$2,$3,NOW(),NOW()) ON CONFLICT DO NOTHING`, [testUser, 'mfa@example.com', 'MFA Test']);
  }, 20000);

  afterAll(async () => {
    await pool.end();
  });

  it('enables TOTP and provides backup codes', async () => {
    const { secret, backupCodes } = await enableTotpForUser(testUser);
    expect(secret).toBeTruthy();
    expect(Array.isArray(backupCodes)).toBe(true);
    expect(backupCodes.length).toBeGreaterThan(0);
  });

  it('verifies a valid TOTP token', async () => {
    const { secret } = await enableTotpForUser(testUser);
    const token = authenticator.generate(secret);
    const ok = await verifyTotp(testUser, token);
    expect(ok).toBe(true);
  });

  it('regenerates and consumes backup codes', async () => {
    const codes = await regenBackupCodes(testUser);
    expect(Array.isArray(codes)).toBe(true);
    const ok = await consumeBackupCode(testUser, codes[0]!);
    expect(ok).toBe(true);
    // consuming again should fail
    const ok2 = await consumeBackupCode(testUser, codes[0]!);
    expect(ok2).toBe(false);
  });

  it('regenerates and consumes recovery codes', async () => {
    const codes = await regenRecoveryCodes(testUser);
    expect(Array.isArray(codes)).toBe(true);
    const ok = await consumeRecoveryCode(testUser, codes[0]!);
    expect(ok).toBe(true);
    const ok2 = await consumeRecoveryCode(testUser, codes[0]!);
    expect(ok2).toBe(false);
  });

  it('can disable MFA and report status', async () => {
    await disableMfaForUser(testUser);
    const status = await getMfaStatus(testUser);
    expect(status.enabled).toBe(false);
  });

  it('creates and verifies an MFA login challenge token', async () => {
    const { secret } = await enableTotpForUser(testUser);
    const memberRow = await pool.query(`SELECT id FROM organization LIMIT 1`);
    const orgId = memberRow.rowCount ? memberRow.rows[0].id : '00000000-0000-0000-0000-000000000000';
    const token = createMfaLoginChallenge(testUser, orgId, ['member']);
    const payload = verifyMfaLoginChallenge(token);
    expect(payload).not.toBeNull();
    expect(payload?.userId).toBe(testUser);
    expect(payload?.organizationId).toBe(orgId);
    expect(payload?.roles).toEqual(['member']);

    const totp = authenticator.generate(secret);
    const verified = await verifyTotp(testUser, totp);
    expect(verified).toBe(true);
  });
});
