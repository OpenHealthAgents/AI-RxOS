import jwt from "jsonwebtoken";

/**
 * Mints an HS256 JWT compatible with apps/api-gateway jwtAuth validation.
 * Attaches multi-tenancy claims (organizationId, roles) to propagate downstream.
 */
export function signLegacyAccessToken(
  userId: string,
  secret: string,
  organizationId: string,
  roles: string[],
  ttlMinutes: number
): string {
  return jwt.sign(
    {
      sub: userId,
      organizationId,
      roles,
    },
    secret,
    {
      algorithm: "HS256",
      expiresIn: `${ttlMinutes}m`,
    }
  );
}
