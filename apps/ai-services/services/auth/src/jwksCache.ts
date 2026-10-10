import { getRedisClient } from './rateLimit.js';
import { config } from './config.js';
import { recordAuditEvent } from './audit.js';

type CacheEntry = { body: any; expiresAt: number };

const inMemoryCache: Map<string, CacheEntry> = new Map();
const DEFAULT_TTL = (config.oidcJwksCacheTtlSeconds ?? 3600) * 1000;
const REFRESH_WINDOW_MS = (config.oidcJwksRefreshWindowSeconds ?? 60) * 1000; // refresh before expiry
const MAX_RETRIES = 3;

async function getRedis(): Promise<any | null> {
  // During tests, avoid initializing Redis client to prevent noisy connection errors
  if (process.env.NODE_ENV === 'test') return null;
  try {
    return await getRedisClient();
  } catch (e) {
    return null;
  }
}

async function fetchWithRetry(url: string): Promise<any> {
  // In test environment, avoid retry/backoff to keep tests fast and deterministic
  const ff = (typeof (globalThis as any).fetch === 'function') ? (globalThis as any).fetch : (await import('node-fetch')).default;
  if (process.env.NODE_ENV === 'test') {
    const res = await ff(url, { method: 'GET' });
    if (!res.ok) throw new Error(`status:${res.status}`);
    return await res.json();
  }

  let attempt = 0;
  let lastErr: any = null;
  while (attempt < MAX_RETRIES) {
    try {
      const res = await ff(url, { method: 'GET' });
      if (!res.ok) throw new Error(`status:${res.status}`);
      const body = await res.json();
      return body;
    } catch (e) {
      lastErr = e;
      attempt++;
      const backoff = 100 * Math.pow(2, attempt);
      // eslint-disable-next-line no-await-in-loop
      await new Promise((r) => setTimeout(r, backoff));
    }
  }
  throw lastErr;
}

export async function getJwks(jwksUri: string): Promise<any> {
  const now = Date.now();
  // check memory cache first
  const mem = inMemoryCache.get(jwksUri);
  if (mem && mem.expiresAt > now) return mem.body;

  // check redis
  const redis = await getRedis();
  if (redis) {
    try {
      const cached = await redis.get(`jwks:${jwksUri}`);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed.expiresAt > now) {
          // populate memory cache
          inMemoryCache.set(jwksUri, { body: parsed.body, expiresAt: parsed.expiresAt });
          return parsed.body;
        }
      }
    } catch (e) {
      // ignore redis read errors
    }
  }

  // fetch and populate caches
  const body = await fetchWithRetry(jwksUri);
  const ttl = DEFAULT_TTL;
  const expiresAt = Date.now() + ttl;
  inMemoryCache.set(jwksUri, { body, expiresAt });
  if (redis) {
    try {
      await redis.set(`jwks:${jwksUri}`, JSON.stringify({ body, expiresAt }), { EX: Math.floor(ttl / 1000) });
    } catch (e) {
      // ignore redis write errors
    }
  }
  return body;
}

export async function forceRefreshJwks(jwksUri: string): Promise<any> {
  try {
    const body = await fetchWithRetry(jwksUri);
    const ttl = DEFAULT_TTL;
    const expiresAt = Date.now() + ttl;
    inMemoryCache.set(jwksUri, { body, expiresAt });
    const redis = await getRedis();
    if (redis) {
      try {
        await redis.set(`jwks:${jwksUri}`, JSON.stringify({ body, expiresAt }), { EX: Math.floor(ttl / 1000) });
      } catch (e) {}
    }
    return body;
  } catch (e) {
    throw e;
  }
}

// Background refresher: periodically scan in-memory cache and refresh near-expiry entries
let refresherRunning = false;
export function startBackgroundRefresh(intervalMs = 30000) {
  if (refresherRunning) return;
  refresherRunning = true;
  setInterval(async () => {
    try {
      const now = Date.now();
      for (const [uri, entry] of Array.from(inMemoryCache.entries())) {
        if (entry.expiresAt - now < REFRESH_WINDOW_MS) {
          try {
            const body = await fetchWithRetry(uri);
            const expiresAt = Date.now() + DEFAULT_TTL;
            inMemoryCache.set(uri, { body, expiresAt });
            const redis = await getRedis();
            if (redis) {
              try {
                await redis.set(`jwks:${uri}`, JSON.stringify({ body, expiresAt }), { EX: Math.floor(DEFAULT_TTL / 1000) });
              } catch (_e) {}
            }
          } catch (e) {
            await recordAuditEvent({ action: 'jwks_refresh_failed', organizationId: null, resourceType: 'jwks', resourceId: uri, metadata: { error: String(e) } });
          }
        }
      }
    } catch (e) {
      // swallow
    }
  }, intervalMs);
}

export function invalidateJwks(jwksUri: string) {
  inMemoryCache.delete(jwksUri);
  // best-effort remove from redis
  getRedis().then((r) => { if (r) r.del(`jwks:${jwksUri}`).catch(() => {}); });
}

export default { getJwks, forceRefreshJwks, startBackgroundRefresh, invalidateJwks };
