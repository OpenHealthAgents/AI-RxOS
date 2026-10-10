import crypto from 'crypto';

export type KeyProviderType = 'env' | 'aws-kms' | 'azure-key-vault' | 'gcp-kms';

export type KeyConfigEntry = {
  version: string;
  provider: KeyProviderType;
  resourceId?: string;
  rawKey?: Buffer;
  createdAt: string;
};

const ENV_KEY_PATTERN = /^MASTER_KEY_V(\d+)$/;
const AWS_KEY_PATTERN = /^AWS_KMS_KEY_V(\d+)$/;
const AZURE_KEY_PATTERN = /^AZURE_KEY_VAULT_KEY_V(\d+)$/;
const GCP_KEY_PATTERN = /^GCP_KMS_KEY_V(\d+)$/;

function parseEnvKeyEntries(): KeyConfigEntry[] {
  const entries: KeyConfigEntry[] = [];
  for (const key of Object.keys(process.env)) {
    const match = key.match(ENV_KEY_PATTERN);
    if (!match) continue;
    const version = `v${match[1]}`;
    const raw = process.env[key];
    if (!raw) continue;
    try {
      const buffer = Buffer.from(raw, 'base64');
      if (buffer.length !== 32) continue;
      entries.push({ version, provider: 'env', rawKey: buffer, createdAt: new Date().toISOString() });
    } catch (_e) {
      // ignore invalid values
    }
  }

  if (entries.length === 0 && process.env.MASTER_KEY) {
    try {
      const buffer = Buffer.from(process.env.MASTER_KEY, 'base64');
      if (buffer.length === 32) {
        entries.push({ version: 'v1', provider: 'env', rawKey: buffer, createdAt: new Date().toISOString() });
      }
    } catch (_e) {
      // ignore invalid MASTER_KEY
    }
  }

  if (entries.length === 0 && process.env.NODE_ENV === 'test') {
    const buffer = Buffer.from('test-master-key-0000000000000000test==', 'utf8').slice(0, 32);
    entries.push({ version: 'v1', provider: 'env', rawKey: buffer, createdAt: new Date().toISOString() });
  }

  return entries.sort((a, b) => a.version.localeCompare(b.version));
}

function parseProviderEntries(pattern: RegExp, provider: KeyProviderType): KeyConfigEntry[] {
  const entries: KeyConfigEntry[] = [];
  for (const key of Object.keys(process.env)) {
    const match = key.match(pattern);
    if (!match) continue;
    const version = `v${match[1]}`;
    const resourceId = process.env[key];
    if (!resourceId) continue;
    entries.push({ version, provider, resourceId, createdAt: new Date().toISOString() });
  }
  return entries.sort((a, b) => a.version.localeCompare(b.version));
}

function hasProviderEntries(pattern: RegExp): boolean {
  return Object.keys(process.env).some((key) => pattern.test(key));
}

export function getKeyManagementProviderType(): KeyProviderType {
  const requested = (process.env.KEY_MANAGEMENT_PROVIDER ?? 'auto').trim().toLowerCase();
  const autoProviders: KeyProviderType[] = [];
  if (hasProviderEntries(AWS_KEY_PATTERN)) autoProviders.push('aws-kms');
  if (hasProviderEntries(AZURE_KEY_PATTERN)) autoProviders.push('azure-key-vault');
  if (hasProviderEntries(GCP_KEY_PATTERN)) autoProviders.push('gcp-kms');

  if (requested === 'auto') {
    if (autoProviders.length > 1) {
      throw new Error('multiple_key_management_providers_configured');
    }
    if (autoProviders.length === 1) return autoProviders[0]!;
    return 'env';
  }

  if (requested === 'env' || requested === 'aws-kms' || requested === 'azure-key-vault' || requested === 'gcp-kms') {
    return requested as KeyProviderType;
  }

  throw new Error(`unsupported_key_management_provider:${requested}`);
}

export function getActiveKeyVersion(): string {
  return process.env.ACTIVE_MASTER_KEY || (process.env.MASTER_KEY_VERSION ? `v${process.env.MASTER_KEY_VERSION}` : 'v1');
}

export function getKeyRegistry(): Map<string, KeyConfigEntry> {
  const provider = getKeyManagementProviderType();
  let entries: KeyConfigEntry[] = [];

  switch (provider) {
    case 'env':
      entries = parseEnvKeyEntries();
      break;
    case 'aws-kms':
      entries = parseProviderEntries(AWS_KEY_PATTERN, 'aws-kms');
      break;
    case 'azure-key-vault':
      entries = parseProviderEntries(AZURE_KEY_PATTERN, 'azure-key-vault');
      break;
    case 'gcp-kms':
      entries = parseProviderEntries(GCP_KEY_PATTERN, 'gcp-kms');
      break;
  }

  const registry = new Map<string, KeyConfigEntry>();
  for (const entry of entries) {
    registry.set(entry.version, entry);
  }

  if (provider !== 'env') {
    for (const entry of parseEnvKeyEntries()) {
      if (!registry.has(entry.version)) {
        registry.set(entry.version, entry);
      }
    }
  }

  if (registry.size === 0 && process.env.NODE_ENV === 'test') {
    const fallback = parseEnvKeyEntries();
    for (const entry of fallback) {
      registry.set(entry.version, entry);
    }
  }

  return registry;
}

async function createAwsKmsClient() {
  const { KMSClient } = await import('@aws-sdk/client-kms');
  return new KMSClient({ region: process.env.AWS_KMS_REGION ?? undefined });
}

async function createAzureCryptographyClient(keyId: string) {
  const { DefaultAzureCredential } = await import('@azure/identity');
  const { CryptographyClient } = await import('@azure/keyvault-keys');
  const credential = new DefaultAzureCredential();
  return new CryptographyClient(keyId, credential);
}

async function createGcpKmsClient() {
  const { KeyManagementServiceClient } = await import('@google-cloud/kms');
  return new KeyManagementServiceClient();
}

export async function generateDataKey(version: string): Promise<{ plainKey: Buffer; encryptedKey?: string; provider: KeyProviderType; createdAt: string }> {
  const registry = getKeyRegistry();
  const entry = registry.get(version);
  if (!entry) {
    throw new Error('unsupported_key_version');
  }

  if (entry.provider === 'env') {
    if (!entry.rawKey) {
      throw new Error('missing_environment_key');
    }
    return {
      plainKey: entry.rawKey,
      provider: 'env',
      createdAt: entry.createdAt,
    };
  }

  if (!entry.resourceId) {
    throw new Error('missing_key_resource_id');
  }

  if (entry.provider === 'aws-kms') {
    const client = await createAwsKmsClient();
    const { GenerateDataKeyCommand } = await import('@aws-sdk/client-kms');
    const result = await client.send(new GenerateDataKeyCommand({ KeyId: entry.resourceId, KeySpec: 'AES_256' }));
    if (!result.Plaintext || !result.CiphertextBlob) {
      throw new Error('aws_kms_generate_data_key_failed');
    }
    return {
      plainKey: Buffer.from(result.Plaintext),
      encryptedKey: Buffer.from(result.CiphertextBlob).toString('base64'),
      provider: 'aws-kms',
      createdAt: entry.createdAt,
    };
  }

  if (entry.provider === 'azure-key-vault') {
    const cryptographyClient = await createAzureCryptographyClient(entry.resourceId);
    const keyBytes = crypto.randomBytes(32);
    const wrapResult = await cryptographyClient.wrapKey('RSA-OAEP', keyBytes);
    if (!wrapResult.result) {
      throw new Error('azure_key_vault_wrap_failed');
    }
    return {
      plainKey: keyBytes,
      encryptedKey: Buffer.from(wrapResult.result).toString('base64'),
      provider: 'azure-key-vault',
      createdAt: entry.createdAt,
    };
  }

  if (entry.provider === 'gcp-kms') {
    const client = await createGcpKmsClient();
    const keyBytes = crypto.randomBytes(32);
    const [encryptResponse] = await client.encrypt({ name: entry.resourceId, plaintext: keyBytes });
    if (!encryptResponse.ciphertext) {
      throw new Error('gcp_kms_encrypt_failed');
    }
    const ciphertext =
      typeof encryptResponse.ciphertext === 'string'
        ? encryptResponse.ciphertext
        : Buffer.from(encryptResponse.ciphertext).toString('base64');
    return {
      plainKey: keyBytes,
      encryptedKey: ciphertext,
      provider: 'gcp-kms',
      createdAt: entry.createdAt,
    };
  }

  throw new Error('unsupported_key_provider');
}

export async function decryptDataKey(version: string, encryptedKey: string): Promise<Buffer> {
  const registry = getKeyRegistry();
  const entry = registry.get(version);
  if (!entry) {
    throw new Error('unsupported_key_version');
  }

  if (entry.provider === 'env') {
    if (!entry.rawKey) {
      throw new Error('missing_environment_key');
    }
    return entry.rawKey;
  }

  if (!entry.resourceId) {
    throw new Error('missing_key_resource_id');
  }

  if (entry.provider === 'aws-kms') {
    const client = await createAwsKmsClient();
    const { DecryptCommand } = await import('@aws-sdk/client-kms');
    const result = await client.send(new DecryptCommand({ CiphertextBlob: Buffer.from(encryptedKey, 'base64') }));
    if (!result.Plaintext) {
      throw new Error('aws_kms_decrypt_failed');
    }
    return Buffer.from(result.Plaintext);
  }

  if (entry.provider === 'azure-key-vault') {
    const cryptographyClient = await createAzureCryptographyClient(entry.resourceId);
    const unwrapResult = await cryptographyClient.unwrapKey('RSA-OAEP', Buffer.from(encryptedKey, 'base64'));
    if (!unwrapResult.result) {
      throw new Error('azure_key_vault_unwrap_failed');
    }
    return Buffer.from(unwrapResult.result);
  }

  if (entry.provider === 'gcp-kms') {
    const client = await createGcpKmsClient();
    const [decryptResponse] = await client.decrypt({ name: entry.resourceId, ciphertext: encryptedKey });
    if (!decryptResponse.plaintext) {
      throw new Error('gcp_kms_decrypt_failed');
    }
    const plaintext = decryptResponse.plaintext;
    return typeof plaintext === 'string' ? Buffer.from(plaintext, 'base64') : Buffer.from(plaintext);
  }

  throw new Error('unsupported_key_provider');
}

export async function decryptLegacyKey(version: string): Promise<Buffer> {
  const envKeys = parseEnvKeyEntries();
  const entry = envKeys.find((item) => item.version === version);
  if (!entry || !entry.rawKey) {
    throw new Error('missing_environment_key_for_legacy_secret');
  }
  return entry.rawKey;
}

export async function getRawKeyForVersion(version: string): Promise<Buffer | null> {
  const registry = getKeyRegistry();
  const entry = registry.get(version);
  if (entry?.rawKey) return entry.rawKey;
  return null;
}
