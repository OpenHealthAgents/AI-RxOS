import { Request, Response, NextFunction } from "express";
import { createClient } from "redis";
import { config } from "./config.js";

let redisClient: ReturnType<typeof createClient> | null = null;

export async function getRedisClient() {
  if (!redisClient) {
    redisClient = createClient({ url: config.redisUrl });
    redisClient.on("error", (err) => {
      // eslint-disable-next-line no-console
      console.error("Redis rate limiter client error:", err);
    });
    await redisClient.connect();
  }
  return redisClient;
}

/**
 * Redis-based Rate Limiting Middleware
 * Evaluates request count for a given Client IP and URL path within a rolling window.
 */
export function rateLimiter(limit: number, windowSeconds: number) {
  return async (req: Request, res: Response, next: NextFunction) => {
    try {
      const client = await getRedisClient();
      const rawIp = req.headers["x-forwarded-for"] || req.socket.remoteAddress || "127.0.0.1";
      let ip = "127.0.0.1";

      if (Array.isArray(rawIp)) {
        ip = rawIp[0] ?? ip;
      } else if (typeof rawIp === "string") {
        ip = rawIp.split(",")[0]?.trim() ?? ip;
      }

      const key = `ratelimit:${ip}:${req.originalUrl || req.path}`;
      const current = await client.incr(key);

      if (current === 1) {
        await client.expire(key, windowSeconds);
      }

      if (current > limit) {
        res.status(429).json({
          code: "rate_limited",
          message: "Too many requests. Please try again later.",
        });
        return;
      }
      next();
    } catch (err) {
      // Fail-closed mode can be enabled for sensitive endpoints in production.
      if (config.rateLimitFailClosed) {
        // eslint-disable-next-line no-console
        console.error("Rate limiting evaluation failed (failing closed):", err);
        res.status(503).json({
          code: "rate_limit_unavailable",
          message: "Rate limiting temporarily unavailable. Please try again later.",
        });
        return;
      }

      // eslint-disable-next-line no-console
      console.error("Rate limiting evaluation failed (failing open):", err);
      next();
    }
  };
}
