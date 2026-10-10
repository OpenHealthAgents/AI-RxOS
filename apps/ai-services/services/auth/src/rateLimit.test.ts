import { describe, expect, it } from "vitest";
import { rateLimitKey, rateLimiter } from "./rateLimit.js";

function request(overrides: Record<string, unknown> = {}) {
  return {
    auth: undefined,
    headers: {},
    method: "POST",
    path: "/api/v1/auth/login",
    socket: { remoteAddress: "192.0.2.10" },
    ...overrides,
  } as never;
}

describe("Redis rate limiter", () => {
  it("creates one bucket per route and does not use caller-controlled forwarded IP", () => {
    const first = request({ headers: { "x-forwarded-for": "198.51.100.1" } });
    const spoofed = request({ headers: { "x-forwarded-for": "203.0.113.9" } });
    expect(rateLimitKey(first)).toBe(rateLimitKey(spoofed));
    expect(rateLimitKey(first)).not.toContain("192.0.2.10");
  });

  it("keys authenticated users by trusted tenant and user identity", () => {
    const userA = request({ auth: { userId: "u1", organizationId: "org-a" } });
    const userB = request({ auth: { userId: "u1", organizationId: "org-b" } });
    expect(rateLimitKey(userA)).not.toBe(rateLimitKey(userB));
  });

  it("does not allow query strings to create additional buckets", () => {
    const base = request({ originalUrl: "/sensitive?attempt=1" });
    const changedQuery = request({ originalUrl: "/sensitive?attempt=2" });
    expect(rateLimitKey(base)).toBe(rateLimitKey(changedQuery));
  });

  it("rejects unbounded or invalid policies", () => {
    expect(() => rateLimiter(0, 60)).toThrow(RangeError);
    expect(() => rateLimiter(1, -1)).toThrow(RangeError);
  });
});
