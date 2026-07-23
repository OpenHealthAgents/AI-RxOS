import crypto from "crypto";
import { dbPool } from "./auth.js";
import { logInfo, logWarn } from "./logger.js";
import { encryptSecret, decryptSecret, EncryptedSecret, getActiveKeyVersion } from "./crypto.js";
import { recordAuditEvent } from "./audit.js";
import jwksCache from './jwksCache.js';
import { config } from "./config.js";

export type OidcProvider = {
  id: string;
  name: string;
  issuer: string;
  clientId: string;
  clientSecret?: string; // returned on create, not stored
  encryptedClientSecret?: EncryptedSecret;
  createdAt: string;
  enabled?: boolean;
  domainHints?: string[];
  priority?: number;
  metadata?: Record<string, any>;
  scopes?: string[];
  responseTypes?: string[];
  health?: {
    lastMetadataFetch?: string;
    lastSuccessfulMetadata?: string;
    consecutiveFailures?: number;
  };
};

export function normalizeIssuer(issuer: string): string {
  return issuer.trim().replace(/\/?$/, "");
}

export function sanitizeOidcProvider(provider: OidcProvider, includeSecret = false): OidcProvider {
  if (includeSecret) return { ...provider };
  const { clientSecret, ...sanitized } = provider;
  return sanitized as OidcProvider;
}

async function getOrganizationSettings(organizationId: string): Promise<any> {
  const cur = await dbPool.query(`SELECT settings FROM organization WHERE id = $1`, [organizationId]);
  if ((cur.rowCount ?? 0) === 0) {
    throw new Error("org_not_found");
  }
  return cur.rows[0].settings ?? {};
}

async function saveOrganizationSettings(organizationId: string, settings: any): Promise<void> {
  await dbPool.query(`UPDATE organization SET settings = $1, updated_at = NOW() WHERE id = $2`, [settings, organizationId]);
}

function normalizeDomainHint(value: string): string {
  return value.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/+$/, "");
}

function getDomainMatchScore(email: string, domainHint: string): number {
  const normalizedEmail = email.trim().toLowerCase();
  const normalizedHint = normalizeDomainHint(domainHint);
  const emailDomain = normalizedEmail.split("@")[1]?.trim().toLowerCase() ?? "";
  if (!normalizedHint || !emailDomain) return 0;
  if (emailDomain === normalizedHint) return 100 + normalizedHint.length;
  if (emailDomain.endsWith(`.${normalizedHint}`)) return 75 + normalizedHint.length;
  return 0;
}

export async function resolveOidcProviderForEmail(
  organizationId: string,
  email: string,
  providersOverride?: OidcProvider[]
): Promise<OidcProvider | null> {
  const providers = providersOverride ?? (await listOidcProviders(organizationId));
  const enabledProviders = providers.filter((provider) => provider.enabled !== false);
  if (enabledProviders.length === 0) return null;

  const candidates = enabledProviders
    .map((provider) => {
      const domainHints: string[] = provider.domainHints ?? [];
      const maxDomainScore = domainHints.reduce<number>((best: number, hint: string) => Math.max(best, getDomainMatchScore(email, hint)), 0);
      return {
        provider,
        matchScore: maxDomainScore,
        priority: provider.priority ?? 0,
      };
    })
    .sort((a, b) => {
      if (b.matchScore !== a.matchScore) return b.matchScore - a.matchScore;
      if (b.priority !== a.priority) return b.priority - a.priority;
      return (a.provider.name || "").localeCompare(b.provider.name || "");
    });

  return candidates[0]?.provider ?? null;
}

export async function validateDynamicClientCredentials(
  organizationId: string,
  clientId: string,
  clientSecret: string
): Promise<boolean> {
  const settings = await getOrganizationSettings(organizationId);
  const clients = settings.oidc_dynamic_clients ?? [];
  const client = clients.find((x: any) => x.client_id === clientId);
  if (!client || !client.encryptedClientSecret) return false;

  const decrypted = await decryptSecret(client.encryptedClientSecret as EncryptedSecret);
  const a = Buffer.from(String(decrypted.plain), "utf8");
  const b = Buffer.from(String(clientSecret), "utf8");
  const max = Math.max(a.length, b.length);
  const aPad = Buffer.alloc(max);
  const bPad = Buffer.alloc(max);
  a.copy(aPad);
  b.copy(bPad);

  try {
    return crypto.timingSafeEqual(aPad, bPad);
  } catch {
    return false;
  }
}

export async function getOrganizationLoginPolicy(organizationId: string): Promise<any> {
  const settings = await getOrganizationSettings(organizationId);
  return settings.sso_policy ?? {
    defaultIdp: null,
    forcedIdp: false,
    domainRouting: true,
    emergencyFallback: null,
  };
}

export async function saveOrganizationLoginPolicy(organizationId: string, policy: any): Promise<any> {
  const settings = await getOrganizationSettings(organizationId);
  const nextSettings = { ...settings, sso_policy: policy };
  await saveOrganizationSettings(organizationId, nextSettings);
  return nextSettings.sso_policy;
}

export async function listOidcProviders(organizationId: string): Promise<OidcProvider[]> {
  const settings = await getOrganizationSettings(organizationId);
  return settings.oidc_providers ?? [];
}

export async function getOidcProvider(organizationId: string, providerId: string): Promise<OidcProvider> {
  const providers = await listOidcProviders(organizationId);
  const provider = providers.find((p) => p.id === providerId);
  if (!provider) throw new Error("provider_not_found");
  return provider;
}

function ensureOidcProviderUniqueness(
  providers: OidcProvider[],
  issuer: string,
  name: string,
  excludeId?: string
) {
  const normalizedIssuer = normalizeIssuer(issuer);
  const conflict = providers.find(
    (p) =>
      p.id !== excludeId &&
      (normalizeIssuer(p.issuer) === normalizedIssuer || p.name === name)
  );
  if (conflict) {
    throw new Error("provider_already_exists");
  }
}

export async function createOidcProvider(
  organizationId: string,
  providerInput: {
    name: string;
    issuer: string;
    clientId: string;
    clientSecret: string;
    enabled?: boolean;
    scopes?: string[];
    responseTypes?: string[];
  },
  opts?: { autoFetchMetadata?: boolean }
): Promise<OidcProvider> {
  const issuer = normalizeIssuer(providerInput.issuer);
  const provider: OidcProvider = {
    id: crypto.randomUUID(),
    name: providerInput.name,
    issuer,
    clientId: providerInput.clientId,
    clientSecret: providerInput.clientSecret,
    createdAt: new Date().toISOString(),
    enabled: providerInput.enabled ?? true,
    scopes: providerInput.scopes,
    responseTypes: providerInput.responseTypes,
  };

  if (opts?.autoFetchMetadata) {
    provider.metadata = await fetchOidcConfiguration(provider.issuer);
  }

  const settings = await getOrganizationSettings(organizationId);
  const providers = settings.oidc_providers ?? [];
  ensureOidcProviderUniqueness(providers, provider.issuer, provider.name);

  // store encrypted secret at rest
  const storageProvider: any = { ...provider };
  if (provider.clientSecret) {
    storageProvider.encryptedClientSecret = await encryptSecret(provider.clientSecret);
    delete storageProvider.clientSecret;
  }

  providers.push(storageProvider);
  await saveOrganizationSettings(organizationId, { ...settings, oidc_providers: providers });
  // return provider object including plaintext secret for immediate response
  return provider;
}

export async function updateOidcProvider(
  organizationId: string,
  providerId: string,
  updates: {
    name?: string;
    issuer?: string;
    clientId?: string;
    clientSecret?: string;
    enabled?: boolean;
    scopes?: string[];
    responseTypes?: string[];
    autoFetchMetadata?: boolean;
  }
): Promise<OidcProvider> {
  const settings = await getOrganizationSettings(organizationId);
  const providers = settings.oidc_providers ?? [];
  const idx = providers.findIndex((p: any) => p.id === providerId);
  if (idx === -1) throw new Error("provider_not_found");

  const current = providers[idx] as OidcProvider;
  const issuer = updates.issuer ? normalizeIssuer(updates.issuer) : current.issuer;
  const name = updates.name ?? current.name;
  ensureOidcProviderUniqueness(providers, issuer, name, providerId);
  const updated: OidcProvider = {
    ...current,
    name,
    issuer,
    clientId: updates.clientId ?? current.clientId,
    // do not store plaintext clientSecret in returned object; store encrypted in settings
    clientSecret: updates.clientSecret ?? current.clientSecret,
    enabled: updates.enabled ?? current.enabled,
    scopes: updates.scopes ?? current.scopes,
    responseTypes: updates.responseTypes ?? current.responseTypes,
  };

  if (updates.issuer && updates.issuer !== current.issuer) {
    updated.metadata = undefined;
  }

  if (updates.autoFetchMetadata) {
    updated.metadata = await fetchOidcConfiguration(updated.issuer);
  }

  providers[idx] = updated;
  // For storage, ensure encryptedClientSecret is set if clientSecret updated
  const storageUpdated = { ...updated } as any;
  if (updates.clientSecret) {
    storageUpdated.encryptedClientSecret = await encryptSecret(updates.clientSecret as string);
    delete storageUpdated.clientSecret;
  }
  providers[idx] = storageUpdated;
  await saveOrganizationSettings(organizationId, { ...settings, oidc_providers: providers });
  return updated;
}

export async function deleteOidcProvider(organizationId: string, providerId: string): Promise<void> {
  const settings = await getOrganizationSettings(organizationId);
  const providers = (settings.oidc_providers ?? []).filter((p: any) => p.id !== providerId);
  await saveOrganizationSettings(organizationId, { ...settings, oidc_providers: providers });
}

export async function refreshOidcProviderMetadata(
  organizationId: string,
  providerId: string,
  issuerOverride?: string
): Promise<Record<string, any>> {
  const settings = await getOrganizationSettings(organizationId);
  const providers = settings.oidc_providers ?? [];
  const idx = providers.findIndex((p: any) => p.id === providerId);
  if (idx === -1) throw new Error("provider_not_found");

  const provider = providers[idx] as OidcProvider;
  const issuer = issuerOverride ? normalizeIssuer(issuerOverride) : provider.issuer;
  const metadata = await fetchOidcConfiguration(issuer);

  const now = new Date().toISOString();
  provider.metadata = metadata;
  provider.issuer = issuer;
  provider.health = provider.health || {};
  provider.health.lastMetadataFetch = now;
  provider.health.lastSuccessfulMetadata = now;
  provider.health.consecutiveFailures = 0;
  providers[idx] = provider;
  await saveOrganizationSettings(organizationId, { ...settings, oidc_providers: providers });
  await recordAuditEvent({ userId: null, organizationId, action: 'refresh_metadata', resourceType: 'oidc_provider', resourceId: providerId, metadata: { issuer } });
  return metadata;
}

async function fetchOidcConfiguration(issuer: string): Promise<Record<string, any>> {
  const metadataUrl = issuer.replace(/\/$/, "") + "/.well-known/openid-configuration";
  logInfo("Fetching OIDC metadata", { issuer, metadataUrl });

  const res = await fetch(metadataUrl, { method: "GET" });
  if (!res.ok) {
    logWarn("OIDC metadata fetch failed", { issuer, status: res.status });
    throw new Error(`metadata_fetch_failed:${res.status}`);
  }

  const metadata = (await res.json()) as any;
  const returnedIssuer = normalizeIssuer(String(metadata.issuer ?? ""));
  if (!returnedIssuer || returnedIssuer !== normalizeIssuer(issuer)) {
    throw new Error("issuer_mismatch");
  }

  if (!metadata.authorization_endpoint || !metadata.token_endpoint || !metadata.jwks_uri) {
    throw new Error("invalid_metadata");
  }

  await fetchJwks(String(metadata.jwks_uri));
  return metadata;
}

async function fetchJwks(jwksUri: string): Promise<any> {
  // use jwksCache module
  const body = await jwksCache.getJwks(jwksUri);
  if (!Array.isArray(body.keys)) throw new Error('invalid_jwks');
  return body;
}

export async function refreshProviderJwks(organizationId: string, providerId: string): Promise<any> {
  const settings = await getOrganizationSettings(organizationId);
  const providers = settings.oidc_providers ?? [];
  const idx = providers.findIndex((p: any) => p.id === providerId);
  if (idx === -1) throw new Error('provider_not_found');
  const provider = providers[idx];
  if (!provider.metadata || !provider.metadata.jwks_uri) throw new Error('jwks_not_configured');
  try {
    const body = await jwksCache.forceRefreshJwks(provider.metadata.jwks_uri);
    const now = new Date().toISOString();
    provider.health = provider.health || {};
    provider.health.lastJwksFetch = now;
    provider.health.consecutiveFailures = 0;
    provider.health.lastSuccessfulJwks = now;
    providers[idx] = provider;
    await saveOrganizationSettings(organizationId, settings);
    await recordAuditEvent({ userId: null, organizationId, action: 'refresh_jwks', resourceType: 'oidc_provider', resourceId: providerId, metadata: { jwks_uri: provider.metadata.jwks_uri } });
    return body;
  } catch (e) {
    provider.health = provider.health || {};
    provider.health.lastJwksFetch = new Date().toISOString();
    provider.health.consecutiveFailures = (provider.health.consecutiveFailures || 0) + 1;
    providers[idx] = provider;
    await saveOrganizationSettings(organizationId, settings);
    await recordAuditEvent({ userId: null, organizationId, action: 'refresh_jwks_failed', resourceType: 'oidc_provider', resourceId: providerId, metadata: { error: String(e) } });
    throw e;
  }
}

/* Dynamic Client Registration (RFC 7591) helpers */
export type DynamicClient = {
  client_id: string;
  client_secret?: string; // returned on creation
  encryptedClientSecret?: { cipherText: string; iv: string; tag: string };
  registration_access_token: string;
  registration_client_uri: string;
  client_id_issued_at: number;
  client_secret_expires_at?: number | null;
  registration_access_token_expires_at?: number | null;
  client_metadata: Record<string, any>;
};

// JWKS cache: jwksUri -> { body, expiresAt }
// legacy local jwksCache removed in favor of shared jwksCache module

function validateRegistrationMetadata(metadata: any) {
  // Basic validation: ensure redirect_uris for code flow
  if (metadata.response_types && metadata.response_types.includes('code')) {
    if (!metadata.redirect_uris || !Array.isArray(metadata.redirect_uris) || metadata.redirect_uris.length === 0) {
      throw new Error('invalid_client_metadata:redirect_uris_required');
    }
  }
}

function makeRegistrationUri(clientId: string) {
  // Use service base URL from config if available
  try {
    const base = (require('./config.js').config as any).betterAuthUrl.replace(/\/$/, '');
    return `${base}/oidc/registration/${clientId}`;
  } catch (_) {
    return `/api/v1/auth/oidc/registration/${clientId}`;
  }
}

export async function createDynamicClient(organizationId: string, metadata: any): Promise<DynamicClient> {
  validateRegistrationMetadata(metadata);
  const settings = await getOrganizationSettings(organizationId);
  const clients = settings.oidc_dynamic_clients ?? [];
  const clientId = crypto.randomUUID();
  const clientSecret = crypto.randomBytes(32).toString('hex');
  const regToken = crypto.randomBytes(32).toString('hex');
  const now = Math.floor(Date.now() / 1000);
  const client: DynamicClient = {
    client_id: clientId,
    client_secret: clientSecret,
    encryptedClientSecret: await encryptSecret(clientSecret),
    registration_access_token: regToken,
    registration_client_uri: makeRegistrationUri(clientId),
    client_id_issued_at: now,
    client_secret_expires_at: null,
    client_metadata: metadata,
  } as any;
  // set optional registration token TTL
  const ttl = config.registrationTokenTtlSeconds ?? 0;
  if (ttl > 0) {
    (client as any).registration_access_token_expires_at = now + ttl;
  } else {
    (client as any).registration_access_token_expires_at = null;
  }
  // store without plaintext secret
  const storage = { ...client } as any;
  delete storage.client_secret;
  clients.push(storage);
  settings.oidc_dynamic_clients = clients;
  await saveOrganizationSettings(organizationId, settings);
  return client;
}

export async function getDynamicClient(organizationId: string, clientId: string, revealSecret = false): Promise<DynamicClient> {
  const settings = await getOrganizationSettings(organizationId);
  const clients = settings.oidc_dynamic_clients ?? [];
  const c = clients.find((x: any) => x.client_id === clientId);
  if (!c) throw new Error('client_not_found');
  const out = { ...c } as any;
  if (revealSecret && c.encryptedClientSecret) {
    const enc = c.encryptedClientSecret as EncryptedSecret;
    const { plain, usedKeyVersion } = await decryptSecret(enc);
    // if secret was encrypted with old key, rotate into active key automatically
    const active = getActiveKeyVersion();
    if (usedKeyVersion !== active) {
      try {
        const newEnc = await encryptSecret(plain);
        // persist change
        const idx = clients.findIndex((x: any) => x.client_id === clientId);
        clients[idx].encryptedClientSecret = newEnc;
        settings.oidc_dynamic_clients = clients;
        await saveOrganizationSettings(organizationId, settings);
        await recordAuditEvent({ userId: null, organizationId, action: 'rotate_secret', resourceType: 'dynamic_client', resourceId: clientId, metadata: { from: usedKeyVersion, to: active } });
      } catch (e) {
        // if rotation fails, log and continue returning plain secret
        await recordAuditEvent({ userId: null, organizationId, action: 'rotate_secret_failed', resourceType: 'dynamic_client', resourceId: clientId, metadata: { error: String(e) } });
      }
    }
    out.client_secret = plain;
  }
  return out;
}

export async function updateDynamicClient(organizationId: string, clientId: string, updates: any, revealSecret = false): Promise<DynamicClient> {
  const settings = await getOrganizationSettings(organizationId);
  const clients = settings.oidc_dynamic_clients ?? [];
  const idx = clients.findIndex((x: any) => x.client_id === clientId);
  if (idx === -1) throw new Error('client_not_found');
  const current = clients[idx];
  // validate
  if (updates.client_metadata) validateRegistrationMetadata(updates.client_metadata);
  const merged = { ...current, client_metadata: { ...current.client_metadata, ...(updates.client_metadata || {}) } };
  clients[idx] = merged;
  settings.oidc_dynamic_clients = clients;
  await saveOrganizationSettings(organizationId, settings);
  const out = { ...merged } as any;
  if (revealSecret && merged.encryptedClientSecret) {
    const enc = merged.encryptedClientSecret as EncryptedSecret;
    const { plain, usedKeyVersion } = await decryptSecret(enc);
    const active = getActiveKeyVersion();
    if (usedKeyVersion !== active) {
      try {
        const newEnc = await encryptSecret(plain);
        clients[idx].encryptedClientSecret = newEnc;
        settings.oidc_dynamic_clients = clients;
        await saveOrganizationSettings(organizationId, settings);
        await recordAuditEvent({ userId: null, organizationId, action: 'rotate_secret', resourceType: 'dynamic_client', resourceId: clientId, metadata: { from: usedKeyVersion, to: active } });
      } catch (e) {
        await recordAuditEvent({ userId: null, organizationId, action: 'rotate_secret_failed', resourceType: 'dynamic_client', resourceId: clientId, metadata: { error: String(e) } });
      }
    }
    out.client_secret = plain;
  }
  return out;
}

export async function deleteDynamicClient(organizationId: string, clientId: string): Promise<void> {
  const settings = await getOrganizationSettings(organizationId);
  const clients = settings.oidc_dynamic_clients ?? [];
  const filtered = clients.filter((x: any) => x.client_id !== clientId);
  settings.oidc_dynamic_clients = filtered;
  await saveOrganizationSettings(organizationId, settings);
}

export async function validateRegistrationAccessToken(organizationId: string, clientId: string, token: string): Promise<boolean> {
  const settings = await getOrganizationSettings(organizationId);
  const clients = settings.oidc_dynamic_clients ?? [];
  const c = clients.find((x: any) => x.client_id === clientId);
  if (!c) return false;
  if (!c.registration_access_token) return false;
  // constant-time compare to avoid timing leaks
  const a = Buffer.from(String(c.registration_access_token), 'utf8');
  const b = Buffer.from(String(token), 'utf8');
  const max = Math.max(a.length, b.length);
  const aPad = Buffer.alloc(max);
  const bPad = Buffer.alloc(max);
  a.copy(aPad);
  b.copy(bPad);
  if (!crypto.timingSafeEqual(aPad, bPad)) return false;
  const now = Math.floor(Date.now() / 1000);
  if (c.registration_access_token_expires_at && c.registration_access_token_expires_at < now) return false;
  // replay protection: attempt to set a short-lived Redis key for this token usage
  try {
    const { getRedisClient } = await import('./rateLimit.js');
    const redis = await getRedisClient();
    const key = `regtoken:used:${organizationId}:${clientId}:${c.registration_access_token}`;
    const setRes = await redis.set(key, '1', { NX: true, EX: 5 });
    if (!setRes) {
      // token was used very recently — treat as potential replay
      return false;
    }
  } catch (e) {
    // if redis unavailable, continue — best-effort
  }

  // update last-used timestamp
  try {
    const idx = clients.findIndex((x: any) => x.client_id === clientId);
    if (idx !== -1) {
      clients[idx].registration_access_token_last_used_at = new Date().toISOString();
      settings.oidc_dynamic_clients = clients;
      await saveOrganizationSettings(organizationId, settings);
    }
  } catch (e) {
    // ignore persistence errors for last-used
  }

  return true;
}

export async function rotateRegistrationAccessToken(organizationId: string, clientId: string): Promise<{ registration_access_token: string; expires_at?: number | null }> {
  const settings = await getOrganizationSettings(organizationId);
  const clients = settings.oidc_dynamic_clients ?? [];
  const idx = clients.findIndex((x: any) => x.client_id === clientId);
  if (idx === -1) throw new Error('client_not_found');
  const newToken = crypto.randomBytes(32).toString('hex');
  const now = Math.floor(Date.now() / 1000);
  const ttl = config.registrationTokenTtlSeconds ?? 0;
  clients[idx].registration_access_token = newToken;
  clients[idx].registration_access_token_expires_at = ttl > 0 ? now + ttl : null;
  clients[idx].registration_access_token_last_rotated_at = new Date().toISOString();
  settings.oidc_dynamic_clients = clients;
  await saveOrganizationSettings(organizationId, settings);
  await recordAuditEvent({ userId: null, organizationId, action: 'rotate_registration_token', resourceType: 'dynamic_client', resourceId: clientId, metadata: { expires_in: ttl } });
  return { registration_access_token: newToken, expires_at: clients[idx].registration_access_token_expires_at };
}

export async function revokeRegistrationAccessToken(organizationId: string, clientId: string): Promise<void> {
  const settings = await getOrganizationSettings(organizationId);
  const clients = settings.oidc_dynamic_clients ?? [];
  const idx = clients.findIndex((x: any) => x.client_id === clientId);
  if (idx === -1) throw new Error('client_not_found');
  clients[idx].registration_access_token = null;
  clients[idx].registration_access_token_expires_at = null;
  settings.oidc_dynamic_clients = clients;
  await saveOrganizationSettings(organizationId, settings);
}

