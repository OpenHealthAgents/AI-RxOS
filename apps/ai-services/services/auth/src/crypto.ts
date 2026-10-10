import crypto from 'crypto';
import { dbPool } from './auth.js';
import { recordAuditEvent } from './audit.js';
import {
  getActiveKeyVersion,
  getRawKeyForVersion,
  generateDataKey,
  decryptDataKey,
  KeyProviderType,
} from './keyManagement.js';

export { getActiveKeyVersion } from './keyManagement.js';

const ALGO = 'aes-256-gcm';
const IV_LENGTH = 12; // recommended for GCM

export type EncryptedSecret = {
  cipherText: string;
  iv: string;
  tag: string;
  keyVersion: string;
  algorithm: string;
  createdAt: string;
  encryptedDataKey?: string;
  keyProvider?: KeyProviderType;
};

export async function encryptSecret(plain: string): Promise<EncryptedSecret> {
  const active = getActiveKeyVersion();
  const dataKey = await generateDataKey(active);
  const key = dataKey.plainKey;
  if (!key) throw new Error('no_active_master_key');
  const iv = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv(ALGO, key, iv);
  const encrypted = Buffer.concat([cipher.update(plain, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  key.fill(0);
  return {
    cipherText: encrypted.toString('base64'),
    iv: iv.toString('base64'),
    tag: tag.toString('base64'),
    keyVersion: active,
    algorithm: ALGO,
    createdAt: new Date().toISOString(),
    encryptedDataKey: dataKey.encryptedKey,
    keyProvider: dataKey.provider,
  };
}

// Decrypt with the key for the provided keyVersion. Returns plaintext and the keyVersion used.
export async function decryptSecret(enc: EncryptedSecret): Promise<{ plain: string; usedKeyVersion: string }> {
  const keyVersion = enc.keyVersion;
  if (!keyVersion) throw new Error('missing_key_version');

  let key: Buffer | null = null;
  if (enc.encryptedDataKey) {
    key = await decryptDataKey(keyVersion, enc.encryptedDataKey);
  } else {
    key = await getRawKeyForVersion(keyVersion);
  }

  if (!key) throw new Error('unsupported_key_version');

  const iv = Buffer.from(enc.iv, 'base64');
  const tag = Buffer.from(enc.tag, 'base64');
  const decipher = crypto.createDecipheriv(enc.algorithm || ALGO, key, iv) as crypto.DecipherGCM;
  decipher.setAuthTag(tag);
  const decryptedBuf = Buffer.concat([decipher.update(Buffer.from(enc.cipherText, 'base64')), decipher.final()]);
  const plain = decryptedBuf.toString('utf8');
  key.fill(0);
  decryptedBuf.fill(0);
  return { plain, usedKeyVersion: keyVersion };
}

// Helper: rotate secrets for a single organization. Will attempt to decrypt using available keys and re-encrypt using active key.
export async function rotateSecretsForOrganization(organizationId: string, opts?: { dryRun?: boolean }): Promise<{ rotated: number; failures: Array<{ id?: string; reason: string }> }> {
  const cur = await dbPool.query(`SELECT settings FROM organization WHERE id = $1`, [organizationId]);
  if ((cur.rowCount ?? 0) === 0) throw new Error('org_not_found');
  const settings = cur.rows[0].settings ?? {};
  let rotated = 0;
  const failures: Array<{ id?: string; reason: string }> = [];
  const providers = settings.oidc_providers ?? [];
  const active = getActiveKeyVersion();
  for (let p of providers) {
    const enc = p.encryptedClientSecret as EncryptedSecret | undefined;
    if (!enc) {
      if (p.clientSecret) {
        if (!opts?.dryRun) {
          p.encryptedClientSecret = await encryptSecret(p.clientSecret);
          delete p.clientSecret;
        }
        rotated++;
        await recordAuditEvent({ userId: null, organizationId, action: 'rotate_secret', resourceType: 'oidc_provider', resourceId: p.id ?? null, metadata: { reason: 'legacy_plaintext' } });
      }
      continue;
    }
    if (enc.keyVersion === active) continue;
    try {
      const { plain } = await decryptSecret(enc as EncryptedSecret);
      if (!opts?.dryRun) {
        p.encryptedClientSecret = await encryptSecret(plain);
      }
      rotated++;
      await recordAuditEvent({ userId: null, organizationId, action: 'rotate_secret', resourceType: 'oidc_provider', resourceId: p.id ?? null, metadata: { from: enc.keyVersion, to: active } });
    } catch (e: any) {
      failures.push({ id: p.id ?? p.issuer ?? undefined, reason: e.message ?? String(e) });
      await recordAuditEvent({ userId: null, organizationId, action: 'rotate_secret_failed', resourceType: 'oidc_provider', resourceId: p.id ?? null, metadata: { error: String(e) } });
    }
  }
  settings.oidc_providers = providers;
  if (rotated > 0 && !opts?.dryRun) {
    await dbPool.query(`UPDATE organization SET settings = $1, updated_at = NOW() WHERE id = $2`, [settings, organizationId]);
  }
  return { rotated, failures };
}

export async function rotateSecretsForAllOrganizations(opts?: { dryRun?: boolean }): Promise<{ totalOrgs: number; totalRotated: number; failures: Record<string, any> }> {
  const all = await dbPool.query(`SELECT id FROM organization`);
  const orgs = all.rows.map((r: any) => r.id);
  let totalRotated = 0;
  const failures: Record<string, any> = {};
  for (const id of orgs) {
    try {
      const res = await rotateSecretsForOrganization(id, opts);
      totalRotated += res.rotated;
      if (res.failures.length > 0) failures[id] = res.failures;
    } catch (e) {
      failures[id] = { error: (e as Error).message };
    }
  }
  return { totalOrgs: orgs.length, totalRotated, failures };
}

// CLI entrypoint helper
export async function rotateAllSecretsCli(argv: string[]): Promise<void> {
  const dry = argv.includes('--dry-run');
  const res = await rotateSecretsForAllOrganizations({ dryRun: dry });
  // eslint-disable-next-line no-console
  console.log('rotate-result', res);
}
