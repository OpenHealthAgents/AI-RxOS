import { createHash } from "crypto";
import type { Request, Response, NextFunction } from "express";
import { createClient } from "redis";
import { config } from "./config.js";

let redisClient: ReturnType<typeof createClient> | null = null;

export async function getRedisClient() {
  if (!redisClient) {
    const client = createClient({ url: config.redisUrl });
    client.on("error", () => {
      // Do not log Redis URLs or connection details that may contain credentials.
      // eslint-disable-next-line no-console
      console.error("Redis rate limiter client error");
    });
    await client.connect();
    redisClient = client;
  }
  return redisClient;
}

const INCREMENT_WITH_EXPIRY = `
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
`;

function rateLimitIdentity(req: Request): string {
  const principal = (req as Request & {
    auth?: { userId?: string; organizationId?: string };
  }).auth;

  if (principal?.userId && principal.organizationId) {
    return `tenant-user:${principal.organizationId}:${principal.userId}`;
  }

  // Forwarded headers are caller-controlled unless an explicitly trusted proxy
  // is configured. Use the transport peer address for unauthenticated callers.
  return `ip:${req.socket.remoteAddress ?? "unknown"}`;
}

export function rateLimitKey(req: Request, namespace = "request"): string {
  const actor = createHash("sha256").update(rateLimitIdentity(req)).digest("hex");
  return `ratelimit:${namespace}:${actor}:${req.method}:${req.path}`;
}

/**
 * Redis-backed fixed-window rate limit shared across service replicas.
 * Use stable route namespaces; query strings must not create new buckets.
 */
export function rateLimiter(limit: number, windowSeconds: number, namespace = "request") {
  if (!Number.isSafeInteger(limit) || limit < 1) {
    throw new RangeError("Rate limit must be a positive integer");
  }
  if (!Number.isSafeInteger(windowSeconds) || windowSeconds < 1) {
    throw new RangeError("Rate limit window must be a positive integer number of seconds");
  }

  return async (req: Request, res: Response, next: NextFunction) => {
    try {
      const client = await getRedisClient();
      const key = rateLimitKey(req, namespace);
      const current = Number(await client.eval(INCREMENT_WITH_EXPIRY, {
        keys: [key],
        arguments: [String(windowSeconds)],
      }));

      if (current > limit) {
        res.status(429).json({
          code: "rate_limited",
          message: "Too many requests. Please try again later.",
        });
        return;
      }
      next();
    } catch {
      if (config.rateLimitFailClosed) {
        // eslint-disable-next-line no-console
        console.error("Rate limit evaluation failed; rejecting request");
        res.status(503).json({
          code: "rate_limit_unavailable",
          message: "Rate limiting temporarily unavailable. Please try again later.",
        });
        return;
      }

      // eslint-disable-next-line no-console
      console.error("Rate limit evaluation failed; proceeding in configured fail-open mode");
      next();
    }
  };
}
