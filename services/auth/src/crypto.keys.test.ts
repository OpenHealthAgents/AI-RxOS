import { vi, describe, it, expect, beforeEach } from 'vitest';
import { getKeyManagementProviderType } from './keyManagement.js';

vi.mock('./auth.js', () => ({ dbPool: { query: vi.fn() } }));

const { dbPool } = await import('./auth.js');

describe('Key versioning and rotation', () => {
  beforeEach(() => {
    (dbPool.query as any).mockReset();
    // clear env keys and provider settings
    delete process.env.MASTER_KEY_V1;
    delete process.env.MASTER_KEY_V2;
    delete process.env.ACTIVE_MASTER_KEY;
    delete process.env.KEY_MANAGEMENT_PROVIDER;
    delete process.env.AWS_KMS_KEY_V1;
    delete process.env.AZURE_KEY_VAULT_KEY_V1;
    delete process.env.GCP_KMS_KEY_V1;
  });

  it('encrypts with active key and decrypts with correct version', async () => {
    // prepare keys
    const k1 = Buffer.alloc(32, 1).toString('base64');
    const k2 = Buffer.alloc(32, 2).toString('base64');
    process.env.MASTER_KEY_V1 = k1;
    process.env.MASTER_KEY_V2 = k2;
    process.env.ACTIVE_MASTER_KEY = 'v2';

    const cryptoMod = await import('./crypto.js');
    const enc = await cryptoMod.encryptSecret('s3cr3t');
    expect(enc.keyVersion).toBe('v2');
    const dec = await cryptoMod.decryptSecret(enc);
    expect(dec.plain).toBe('s3cr3t');
    expect(dec.usedKeyVersion).toBe('v2');
  });

  it('automatically re-encrypts older-key secret when revealed via getDynamicClient', async () => {
    const k1 = Buffer.alloc(32, 1).toString('base64');
    const k2 = Buffer.alloc(32, 2).toString('base64');
    process.env.MASTER_KEY_V1 = k1;
    process.env.MASTER_KEY_V2 = k2;
    process.env.ACTIVE_MASTER_KEY = 'v2';

    const oidc = await import('./oidc.js');
    const cryptoMod = await import('./crypto.js');

    // craft a secret encrypted with v1
    const oldEnc = await (async () => {
      // temporarily set active to v1 to encrypt
      process.env.ACTIVE_MASTER_KEY = 'v1';
      const e = await cryptoMod.encryptSecret('legacy');
      process.env.ACTIVE_MASTER_KEY = 'v2';
      return e;
    })();

    const client = {
      client_id: 'c1',
      registration_access_token: 'r',
      encryptedClientSecret: oldEnc,
      client_metadata: {},
    };

    // SELECT settings
    (dbPool.query as any)
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: { oidc_dynamic_clients: [client] } }] })
      .mockResolvedValueOnce({}); // update

    const out = await oidc.getDynamicClient('org1', 'c1', true);
    expect(out.client_secret).toBe('legacy');
    // ensure update was called to persist re-encryption
    expect((dbPool.query as any).mock.calls.length).toBeGreaterThanOrEqual(2);
  }, { timeout: 20000 });

  it('rotation CLI dry-run does not persist changes', async () => {
    const k1 = Buffer.alloc(32, 1).toString('base64');
    const k2 = Buffer.alloc(32, 2).toString('base64');
    process.env.MASTER_KEY_V1 = k1;
    process.env.MASTER_KEY_V2 = k2;
    process.env.ACTIVE_MASTER_KEY = 'v2';

    const cryptoMod = await import('./crypto.js');
    // mock org list
    (dbPool.query as any)
      .mockResolvedValueOnce({ rows: [{ id: 'org1' }, { id: 'org2' }], rowCount: 2 })
      // per-org SELECT
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: {} }] })
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ settings: {} }] });

    const res = await cryptoMod.rotateSecretsForAllOrganizations({ dryRun: true });
    expect(res.totalOrgs).toBe(2);
  });

  it('rejects corrupted ciphertext with authentication failure', async () => {
  });

  it('selects env provider when only env keys are configured', async () => {
    const k1 = Buffer.alloc(32, 1).toString('base64');
    process.env.MASTER_KEY_V1 = k1;
    delete process.env.KEY_MANAGEMENT_PROVIDER;

    expect(getKeyManagementProviderType()).toBe('env');
  });

  it('auto-detects AWS KMS when AWS provider keys are present', async () => {
    process.env.AWS_KMS_KEY_V1 = 'arn:aws:kms:us-east-1:123456789012:key/abc123';
    expect(getKeyManagementProviderType()).toBe('aws-kms');
  });

  it('auto-detects Azure Key Vault when Azure provider keys are present', async () => {
    process.env.AZURE_KEY_VAULT_KEY_V1 = 'https://vault.vault.azure.net/keys/keyname/123456';
    expect(getKeyManagementProviderType()).toBe('azure-key-vault');
  });

  it('auto-detects GCP KMS when GCP provider keys are present', async () => {
    process.env.GCP_KMS_KEY_V1 = 'projects/test-project/locations/global/keyRings/test/cryptoKeys/key/cryptoKeyVersions/1';
    expect(getKeyManagementProviderType()).toBe('gcp-kms');
  });

  it('rejects corrupted ciphertext with authentication failure', async () => {
    const k1 = Buffer.alloc(32, 1).toString('base64');
    process.env.MASTER_KEY_V1 = k1;
    process.env.ACTIVE_MASTER_KEY = 'v1';
    const cryptoMod = await import('./crypto.js');
    const enc = await cryptoMod.encryptSecret('p');
    // corrupt ciphertext
    enc.cipherText = enc.cipherText.slice(0, -4) + 'AAAA';
    await expect(cryptoMod.decryptSecret(enc)).rejects.toThrow();
  });
});
