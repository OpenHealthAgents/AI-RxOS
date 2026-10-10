import jwt from "jsonwebtoken";

/**
 * Mints an HS256 JWT with the same claim shape services/auth issues
 * (internal/handlers/auth.go issueTokens: sub + iat + exp), signed with
 * the same JWT_SECRET, so apps/api-gateway's existing jwtAuth middleware
 * (internal/gateway/middleware.go) accepts it unchanged.
 *
 * BetterAuth's own JWT plugin (see auth.ts) cannot do this: it only
 * supports asymmetric algorithms (EdDSA/ES256/ES512/RS256/PS256/ECDH-ES),
 * not HS256 with a static shared secret — verified against
 * https://www.better-auth.com/docs/plugins/jwt. This function is the
 * documented bridge point between a BetterAuth session and the legacy
 * token contract; it is not yet called from any route (see README.md
 * "BetterAuth adapter" for what's needed to wire it into a real sign-in
 * flow).
 */
export function signLegacyAccessToken(userId: string, secret: string, ttlMinutes: number): string {
  return jwt.sign({ sub: userId }, secret, {
    algorithm: "HS256",
    expiresIn: `${ttlMinutes}m`,
  });
}
