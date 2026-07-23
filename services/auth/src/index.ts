console.log("===== NEW INDEX.TS LOADED =====");
import express from "express";
import { toNodeHandler } from "better-auth/node";
import crypto from "crypto";
import path from "path";
import { fileURLToPath } from "url";
import "dotenv/config";
console.log("BETTER_AUTH_SECRET =", process.env.BETTER_AUTH_SECRET);

import { auth, dbPool } from "./auth.js";
import { config } from "./config.js";
import { initDatabase } from "./db.js";
import { rateLimiter, getRedisClient } from "./rateLimit.js";
import { signLegacyAccessToken } from "./legacyToken.js";
import { recordAuditEvent } from "./audit.js";
import { verifyAuditLogRecord } from "./auditVerification.js";
import { tenantContextMiddleware } from "./tenantContext.js";
import {
  enableTotpForUser,
  disableMfaForUser,
  getTotpQr,
  verifyTotp,
  regenBackupCodes,
  consumeBackupCode,
  regenRecoveryCodes,
  consumeRecoveryCode,
  getMfaStatus,
  getUserMfaEnabled,
  createMfaLoginChallenge,
  verifyMfaLoginChallenge,
} from "./mfa.js";
import {
  evaluateABAC,
  type SubjectAttributes,
  type ResourceAttributes,
  type Action,
  type EnvironmentAttributes,
} from "./abac.js";
import { requireRole } from "./rbac.js";
import {
  createOidcProvider,
  deleteOidcProvider,
  getOidcProvider,
  listOidcProviders,
  refreshOidcProviderMetadata,
  sanitizeOidcProvider,
  updateOidcProvider,
} from "./oidc.js";
const app = express();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Serve lightweight admin static UI for session/device management
const publicDir = path.resolve(__dirname, "../public");
app.use("/admin", express.static(publicDir));

app.use(express.json());
app.use(tenantContextMiddleware);

// alias admin pages for convenience
app.get('/admin/sessions', (_req, res) => {
  res.sendFile(path.join(publicDir, 'sessions.html'));
});
app.get('/admin/passkeys', (_req, res) => {
  res.sendFile(path.join(publicDir, 'passkeys.html'));
});

// 1. Health Checks
app.get("/healthz", (_req, res) => {
  res.json({ status: "ok", service: "auth" });
});

app.get("/api/v1/auth/audit/verify/:id", async (req, res) => {
  const auditId = req.params.id;
  const authPayload = (req as any).auth;

  if (!authPayload) {
    res.status(401).json({ code: "unauthorized", message: "Authentication required" });
    return;
  }

  if (!auditId) {
    res.status(400).json({ code: "invalid_request", message: "Audit record id is required" });
    return;
  }

  try {
    const verified = await verifyAuditLogRecord(auditId);
    res.json({ id: auditId, verified });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("Audit verification failed:", err);
    res.status(500).json({ code: "verify_failed", message: "Audit verification failed" });
  }
});

// MFA endpoints
app.post('/api/v1/auth/mfa/enable', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  try {
    const { secret, backupCodes } = await enableTotpForUser(auth.userId);
    res.json({ secret, backupCodes });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Enable MFA failed', e);
    res.status(500).json({ code: 'enable_failed' });
  }
});

app.post('/api/v1/auth/mfa/disable', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  try {
    await disableMfaForUser(auth.userId);
    res.json({ ok: true });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Disable MFA failed', e);
    res.status(500).json({ code: 'disable_failed' });
  }
});

app.get('/api/v1/auth/mfa/qrcode', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  try {
    const { dataUrl } = await getTotpQr(auth.userId);
    res.json({ qr: dataUrl });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Get QR failed', e);
    res.status(500).json({ code: 'qr_failed' });
  }
});

app.post('/api/v1/auth/mfa/verify', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  const { token } = req.body as { token?: string };
  if (!token) return res.status(400).json({ code: 'invalid_body' });
  try {
    const ok = await verifyTotp(auth.userId, token);
    res.json({ ok });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Verify TOTP failed', e);
    res.status(500).json({ code: 'verify_failed' });
  }
});

app.post('/api/v1/auth/mfa/backup/regenerate', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  try {
    const codes = await regenBackupCodes(auth.userId);
    res.json({ codes });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Regenerate backup codes failed', e);
    res.status(500).json({ code: 'regen_failed' });
  }
});

app.post('/api/v1/auth/mfa/backup/consume', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  const { code } = req.body as { code?: string };
  if (!code) return res.status(400).json({ code: 'invalid_body' });
  try {
    const ok = await consumeBackupCode(auth.userId, code);
    res.json({ ok });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Consume backup code failed', e);
    res.status(500).json({ code: 'consume_failed' });
  }
});

app.post('/api/v1/auth/mfa/recovery/regenerate', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  try {
    const codes = await regenRecoveryCodes(auth.userId);
    res.json({ codes });
  } catch (e) {
    console.error('Regenerate recovery codes failed', e);
    res.status(500).json({ code: 'regen_failed' });
  }
});

app.post('/api/v1/auth/mfa/recovery/consume', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  const { code } = req.body as { code?: string };
  if (!code) return res.status(400).json({ code: 'invalid_body' });
  try {
    const ok = await consumeRecoveryCode(auth.userId, code);
    res.json({ ok });
  } catch (e) {
    console.error('Consume recovery code failed', e);
    res.status(500).json({ code: 'consume_failed' });
  }
});

app.post('/api/v1/auth/mfa/login/verify', async (req, res) => {
  const { challengeToken, method, value } = req.body as { challengeToken?: string; method?: string; value?: string };
  if (!challengeToken || !method || !value) {
    res.status(400).json({ code: 'invalid_body', message: 'challengeToken, method, and value are required' });
    return;
  }

  const payload = verifyMfaLoginChallenge(challengeToken);
  if (!payload) {
    res.status(400).json({ code: 'invalid_challenge', message: 'Challenge token is invalid or expired' });
    return;
  }

  let verified = false;
  try {
    switch (method) {
      case 'totp':
        verified = await verifyTotp(payload.userId, value);
        break;
      case 'backup':
        verified = await consumeBackupCode(payload.userId, value);
        break;
      case 'recovery':
        verified = await consumeRecoveryCode(payload.userId, value);
        break;
      default:
        res.status(400).json({ code: 'invalid_method', message: 'Unsupported MFA method' });
        return;
    }
  } catch (e) {
    console.error('MFA login verification failed', e);
    res.status(500).json({ code: 'verify_failed' });
    return;
  }

  if (!verified) {
    res.status(401).json({ code: 'mfa_failed', message: 'MFA verification failed' });
    return;
  }

  const accessToken = signLegacyAccessToken(
    payload.userId,
    config.jwtSecret,
    payload.organizationId,
    payload.roles,
    config.jwtAccessTtlMinutes
  );
  const refreshToken = crypto.randomUUID();

  try {
    await dbPool.query(
      `INSERT INTO session (id, user_id, token, expires_at, ip_address, user_agent)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [crypto.randomUUID(), payload.userId, refreshToken, new Date(Date.now() + config.jwtRefreshTtlDays * 24 * 60 * 60 * 1000).toISOString(), req.headers['x-forwarded-for'] as string ?? req.socket.remoteAddress, req.headers['user-agent']]
    );
  } catch (e) {
    console.error('Failed to create session row after MFA verification:', e);
  }

  await recordAuditEvent({
    userId: payload.userId,
    organizationId: payload.organizationId,
    action: 'mfa_login_verified',
    resourceType: 'session',
    resourceId: payload.userId,
    ipAddress: (req.headers['x-forwarded-for'] as string) || req.socket.remoteAddress,
    userAgent: req.headers['user-agent'],
    metadata: { method },
  });

  await getRedisClient().then((redis) =>
    redis.set(
      `refresh:${refreshToken}`,
      JSON.stringify({ userId: payload.userId, organizationId: payload.organizationId, roles: payload.roles }),
      { EX: config.jwtRefreshTtlDays * 24 * 60 * 60 }
    )
  );

  res.json({ accessToken, refreshToken, expiresIn: config.jwtAccessTtlMinutes * 60 });
});

app.get('/api/v1/auth/mfa/status', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  try {
    const status = await getMfaStatus(auth.userId);
    res.json(status);
  } catch (e) {
    console.error('Get MFA status failed', e);
    res.status(500).json({ code: 'status_failed' });
  }
});

// Admin: set organization-level MFA policy
app.post('/api/v1/auth/admin/mfa/policy', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  const { organizationId, mfaRequired } = req.body as { organizationId?: string; mfaRequired?: boolean };
  if (!organizationId || typeof mfaRequired !== 'boolean') return res.status(400).json({ code: 'invalid_body' });
  try {
    // ensure caller is owner of the organization
    const member = await dbPool.query('SELECT role FROM member WHERE organization_id = $1 AND user_id = $2 LIMIT 1', [organizationId, auth.userId]);
    if (member.rowCount === 0 || member.rows[0].role !== 'owner') return res.status(403).json({ code: 'forbidden' });
    await dbPool.query('UPDATE organization SET mfa_required = $2 WHERE id = $1', [organizationId, mfaRequired]);
    res.json({ ok: true });
  } catch (e) {
    console.error('Set MFA policy failed', e);
    res.status(500).json({ code: 'set_failed' });
  }
});

app.get('/api/v1/auth/admin/mfa/policy/:organizationId', async (req, res) => {
  const auth = (req as any).auth;
  if (!auth) return res.status(401).json({ code: 'unauthorized' });
  const organizationId = req.params.organizationId;
  try {
    const member = await dbPool.query('SELECT role FROM member WHERE organization_id = $1 AND user_id = $2 LIMIT 1', [organizationId, auth.userId]);
    if (member.rowCount === 0 || member.rows[0].role !== 'owner') return res.status(403).json({ code: 'forbidden' });
    const r = await dbPool.query('SELECT mfa_required FROM organization WHERE id = $1', [organizationId]);
    res.json({ mfaRequired: r.rowCount ? r.rows[0].mfa_required : false });
  } catch (e) {
    console.error('Get MFA policy failed', e);
    res.status(500).json({ code: 'get_failed' });
  }
});

// 2. Legacy / Backwards-compatible Registration
// POST /api/v1/auth/register
//
// Flow:
//   1. Create user via BetterAuth (signUpEmail)
//   2. Create tenant org via direct SQL insert
//   3. Insert member row via direct SQL insert
//   4. Issue legacy HS256 JWT for gateway compatibility
//   5. Issue & store refresh token in Redis
//
// Why direct SQL for org/member:
//   auth.api.createOrganization requires a live BetterAuth session (cookie/headers).
//   At registration time no browser session exists yet. Direct SQL is the correct
//   server-side approach for BetterAuth v1.6.23.

app.post("/api/v1/auth/register", rateLimiter(10, 60), async (req, res) => {
  const { email, password, displayName, organizationId } = req.body as {
    email?: string;
    password?: string;
    displayName?: string;
    organizationId?: string;
  };

  if (!email || !password || password.length < 8) {
    res.status(400).json({
      code: "invalid_input",
      message: "email required, password must be >= 8 chars",
    });
    return;
  }

  try {
    // Step 1 — Create user via BetterAuth
    const userName =
  displayName?.trim() ||
  email.split("@").at(0) ||
  "user";

const userSession = await auth.api.signUpEmail({
  body: {
    email,
    password,
    name: userName,
  },
});

    if (!userSession || !userSession.user) {
      res.status(500).json({
        code: "registration_failed",
        message: "BetterAuth registration failed",
      });
      return;
    }

    const userId = userSession.user.id;

    // Step 2 — Resolve or create tenant organization
    // BetterAuth uses camelCase column names with the pg adapter.
    let finalOrgId: string;

    if (organizationId) {
      // Caller provided an existing org — verify it exists
      const orgCheck = await dbPool.query(
        `SELECT id FROM organization WHERE id = $1`,
        [organizationId]
      );
      if ((orgCheck.rowCount ?? 0) === 0) {
        res.status(400).json({
          code: "org_not_found",
          message: "The specified organizationId does not exist",
        });
        return;
      }
      finalOrgId = organizationId;
    } else {
      // Create a new organization for this user (one per registration)
      finalOrgId = crypto.randomUUID();
      const organizationName = (req.body as { organizationName?: string }).organizationName;

const orgName =
  organizationName ??
  displayName ??
  userName;

const slug = orgName
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, "-");
      await dbPool.query(
        `INSERT INTO organization (id, name, slug, "createdAt")
         VALUES ($1, $2, $3, NOW())
         ON CONFLICT DO NOTHING`,
        [finalOrgId, orgName, slug]
      );
    }

    // Step 3 — Insert member row (idempotent)
    const memberCheck = await dbPool.query(
      `SELECT 1 FROM member WHERE "organizationId" = $1 AND "userId" = $2`,
      [finalOrgId, userId]
    );
    if ((memberCheck.rowCount ?? 0) === 0) {
      await dbPool.query(
        `INSERT INTO member (id, "organizationId", "userId", role, "createdAt")
         VALUES ($1, $2, $3, $4, NOW())`,
        [crypto.randomUUID(), finalOrgId, userId, "owner"]
      );
    }

    // Step 4 — Issue gateway-compatible access token (HS256) and refresh token
    const roles = ["owner"];
    const accessToken = signLegacyAccessToken(
      userId,
      config.jwtSecret,
      finalOrgId,
      roles,
      config.jwtAccessTtlMinutes
    );
    const refreshToken = crypto.randomUUID();

    // Step 5 — Store refresh token in Redis for validation/rotation
    const redis = await getRedisClient();
    await redis.set(
      `refresh:${refreshToken}`,
      JSON.stringify({ userId, organizationId: finalOrgId, roles }),
      { EX: config.jwtRefreshTtlDays * 24 * 60 * 60 }
    );

    // Write log to the append-only Audit Logs table
    await recordAuditEvent({
      userId,
      organizationId: finalOrgId,
      action: "register",
      resourceType: "user",
      resourceId: userId,
      ipAddress:
        (req.headers["x-forwarded-for"] as string) ||
        req.socket.remoteAddress,
      userAgent: req.headers["user-agent"],
      metadata: { email, displayName },
    });

    res.json({
      accessToken,
      refreshToken,
      expiresIn: config.jwtAccessTtlMinutes * 60,
    });
  } catch (err: unknown) {
    const error = err as { message?: string; code?: string };
    if (
      error.message?.includes("already exists") ||
      error.code === "email_taken"
    ) {
      res.status(409).json({
        code: "email_taken",
        message: "an account with this email already exists",
      });
      return;
    }
    res.status(500).json({
      code: "create_failed",
      message: error.message || "Internal server error",
    });
  }
});

// 3. Legacy / Backwards-compatible Login
console.log("Register route loaded");
app.post("/api/v1/auth/login", rateLimiter(10, 60), async (req, res) => {
  const { email, password } = req.body as {
    email?: string;
    password?: string;
  };

  if (!email || !password) {
    res.status(400).json({
      code: "invalid_input",
      message: "email and password are required",
    });
    return;
  }

  try {
    const redis = await getRedisClient();

    // Brute-force: check account lock
    const lockKey = `bf:lock:${email}`;
    const lockTtl = await redis.ttl(lockKey);
    if (lockTtl && lockTtl > 0) {
      res.status(423).json({
        code: "account_locked",
        message: `Account locked due to too many failed attempts. Try again in ${lockTtl} seconds`,
      });
      return;
    }

    const userSession = await auth.api.signInEmail({
      body: {
        email,
        password,
      },
    });

    if (!userSession || !userSession.user) {
      res.status(401).json({
        code: "invalid_credentials",
        message: "email or password is incorrect",
      });
      return;
    }

    const userId = userSession.user.id;

    // Resolve tenant membership and roles via direct SQL.
    // BetterAuth manages the member table; camelCase columns with pg adapter.
    const memberRes = await dbPool.query(
      `SELECT "organizationId", role FROM member WHERE "userId" = $1 ORDER BY "createdAt" ASC LIMIT 1`,
      [userId]
    );

    let orgId: string = crypto.randomUUID();
    let roles = ["member"];

    if ((memberRes.rowCount ?? 0) > 0) {
      orgId = memberRes.rows[0].organizationId as string;
      roles = [memberRes.rows[0].role as string];
    }

    const mfaRequiredResult = await dbPool.query(
      `SELECT mfa_required FROM organization WHERE id = $1`,
      [orgId]
    );
    const mfaRequired = (mfaRequiredResult.rowCount ?? 0) > 0 && mfaRequiredResult.rows[0].mfa_required === true;
    const mfaEnabled = await getUserMfaEnabled(userId);

    if (mfaRequired && !mfaEnabled) {
      res.status(403).json({
        code: 'mfa_required',
        message: 'Organization requires MFA, but user has not enabled it',
      });
      return;
    }

    if (mfaRequired && mfaEnabled) {
      const challengeToken = createMfaLoginChallenge(userId, orgId, roles);
      await recordAuditEvent({
        userId,
        organizationId: orgId,
        action: 'mfa_challenge_issued',
        resourceType: 'session',
        resourceId: userId,
        ipAddress: (req.headers['x-forwarded-for'] as string) || req.socket.remoteAddress,
        userAgent: req.headers['user-agent'],
        metadata: { method: 'totp_or_backup_or_recovery' },
      });
      res.status(202).json({
        code: 'mfa_challenge',
        challengeToken,
        methods: ['totp', 'backup', 'recovery'],
      });
      return;
    }

    const accessToken = signLegacyAccessToken(
      userId,
      config.jwtSecret,
      orgId,
      roles,
      config.jwtAccessTtlMinutes
    );
    const refreshToken = crypto.randomUUID();

    await redis.set(
      `refresh:${refreshToken}`,
      JSON.stringify({ userId, organizationId: orgId, roles }),
      { EX: config.jwtRefreshTtlDays * 24 * 60 * 60 }
    );

    // Clear any failed login counters on successful login
    await redis.del(`bf:fail:${email}`);
    await redis.del(lockKey);

    // Create server-side session record for device/session management
    try {
      const expiresAt = new Date(Date.now() + config.jwtRefreshTtlDays * 24 * 60 * 60 * 1000);
      await dbPool.query(
        `INSERT INTO session (id, user_id, token, expires_at, ip_address, user_agent)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [crypto.randomUUID(), userId, refreshToken, expiresAt.toISOString(), (req.headers["x-forwarded-for"] as string) ?? req.socket.remoteAddress, req.headers["user-agent"]]
      );
    } catch (e) {
      // Log but do not fail login
      // eslint-disable-next-line no-console
      console.error("Failed to create session row:", e);
    }

    await recordAuditEvent({
      userId,
      organizationId: orgId,
      action: "login",
      resourceType: "session",
      resourceId: userId,
      ipAddress:
        (req.headers["x-forwarded-for"] as string) ||
        req.socket.remoteAddress,
      userAgent: req.headers["user-agent"],
      metadata: { email },
    });

    res.json({
      accessToken,
      refreshToken,
      expiresIn: config.jwtAccessTtlMinutes * 60,
    });
  } catch (_err: unknown) {
    // On authentication failure, increment failed-attempt counter and lock if threshold exceeded
    try {
      const redis = await getRedisClient();
      const failKey = `bf:fail:${email}`;
      const fails = await redis.incr(failKey);
      if (fails === 1) {
        await redis.expire(failKey, config.failedLoginWindowSeconds);
      }

      if (fails >= config.maxFailedLoginAttempts) {
        const lockKey = `bf:lock:${email}`;
        await redis.set(lockKey, "1", { EX: config.accountLockoutSeconds });
        await recordAuditEvent({
          userId: null,
          organizationId: null,
          action: "account_locked",
          resourceType: "user",
          resourceId: null,
          ipAddress: (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress,
          userAgent: req.headers["user-agent"],
          metadata: { email, failedAttempts: fails },
        });
      } else {
        await recordAuditEvent({
          userId: null,
          organizationId: null,
          action: "failed_login",
          resourceType: "user",
          resourceId: null,
          ipAddress: (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress,
          userAgent: req.headers["user-agent"],
          metadata: { email, failedAttempts: fails },
        });
      }
    } catch (e) {
      // ignore rate-limiter failures
      // eslint-disable-next-line no-console
      console.error("Error updating brute-force counters:", e);
    }

    res.status(401).json({
      code: "invalid_credentials",
      message: "email or password is incorrect",
    });
  }
});

// 4. Legacy Refresh Token Adapter (with rotation)
app.post("/api/v1/auth/refresh", async (req, res) => {
  const { refreshToken } = req.body as { refreshToken?: string };
  if (!refreshToken) {
    res.status(400).json({
      code: "invalid_body",
      message: "refreshToken is required",
    });
    return;
  }

  try {
    const redis = await getRedisClient();
    const sessionData = await redis.get(`refresh:${refreshToken}`);
    if (!sessionData) {
      res.status(401).json({
        code: "invalid_refresh_token",
        message: "refresh token is invalid or expired",
      });
      return;
    }

    const { userId, organizationId, roles } = JSON.parse(sessionData) as {
      userId: string;
      organizationId: string;
      roles: string[];
    };

    // Rotate refresh token: invalidate previous one
    await redis.del(`refresh:${refreshToken}`);

    // Remove old session row (if exists)
    try {
      await dbPool.query(`DELETE FROM session WHERE token = $1`, [refreshToken]);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("Failed to delete old session row:", e);
    }

    const newAccessToken = signLegacyAccessToken(
      userId,
      config.jwtSecret,
      organizationId,
      roles,
      config.jwtAccessTtlMinutes
    );
    const newRefreshToken = crypto.randomUUID();

    await redis.set(
      `refresh:${newRefreshToken}`,
      JSON.stringify({ userId, organizationId, roles }),
      { EX: config.jwtRefreshTtlDays * 24 * 60 * 60 }
    );

    // Create new session row
    try {
      const expiresAt = new Date(Date.now() + config.jwtRefreshTtlDays * 24 * 60 * 60 * 1000);
      await dbPool.query(
        `INSERT INTO session (id, user_id, token, expires_at, ip_address, user_agent)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [crypto.randomUUID(), userId, newRefreshToken, expiresAt.toISOString(), (req.headers["x-forwarded-for"] as string) ?? req.socket.remoteAddress, req.headers["user-agent"]]
      );
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("Failed to create session row on refresh:", e);
    }

    await recordAuditEvent({
      userId,
      organizationId,
      action: "refresh_token",
      resourceType: "session",
      ipAddress:
        (req.headers["x-forwarded-for"] as string) ||
        req.socket.remoteAddress,
      userAgent: req.headers["user-agent"],
    });

    res.json({
      accessToken: newAccessToken,
      refreshToken: newRefreshToken,
      expiresIn: config.jwtAccessTtlMinutes * 60,
    });
  } catch (err: unknown) {
    const error = err as { message?: string };
    res.status(500).json({
      code: "refresh_failed",
      message: error.message || "Internal server error",
    });
  }
});

// Logout: revoke refresh token and remove server-side session
app.post("/api/v1/auth/logout", async (req, res) => {
  const { refreshToken } = req.body as { refreshToken?: string };
  if (!refreshToken) {
    res.status(400).json({ code: "invalid_body", message: "refreshToken is required" });
    return;
  }

  try {
    const redis = await getRedisClient();
    await redis.del(`refresh:${refreshToken}`);
    try {
      await dbPool.query(`DELETE FROM session WHERE token = $1`, [refreshToken]);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("Failed to delete session row on logout:", e);
    }

    await recordAuditEvent({
      userId: null,
      organizationId: null,
      action: "logout",
      resourceType: "session",
      resourceId: null,
      ipAddress: (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress,
      userAgent: req.headers["user-agent"],
    });

    res.status(204).send(null);
  } catch (e: unknown) {
    // eslint-disable-next-line no-console
    console.error("Logout failed:", e);
    res.status(500).json({ code: "logout_failed", message: "Internal server error" });
  }
});

// 5. ABAC Policy Evaluation Endpoint
app.post("/api/v1/auth/abac/evaluate", async (req, res) => {
  const { subject, resource, action, environment } = req.body as {
    subject: SubjectAttributes;
    resource: ResourceAttributes;
    action: Action;
    environment?: EnvironmentAttributes;
  };

  if (!subject || !resource || !action) {
    res.status(400).json({ code: "invalid_body", message: "subject, resource, and action are required" });
    return;
  }

  try {
    const result = await evaluateABAC({ subject, resource, action, environment });
    res.json(result);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("ABAC evaluation failed:", e);
    res.status(500).json({ code: "abac_error", message: "ABAC evaluation failed" });
  }
});

function parseUserAgent(userAgent: string | null | undefined) {
  if (!userAgent) {
    return { browser: "Unknown", os: "Unknown" };
  }
  const ua = userAgent;
  const browser = (() => {
    if (/Edg\//.test(ua) || /Edge\//.test(ua)) return "Edge";
    if (/OPR\//.test(ua) || /Opera\//.test(ua)) return "Opera";
    if (/Chrome\//.test(ua) && !/Chromium\//.test(ua)) return "Chrome";
    if (/Firefox\//.test(ua)) return "Firefox";
    if (/Safari\//.test(ua) && !/Chrome\//.test(ua) && !/Chromium\//.test(ua)) return "Safari";
    if (/Chromium\//.test(ua)) return "Chromium";
    return "Unknown";
  })();

  const os = (() => {
    if (/Windows NT 10/.test(ua)) return "Windows 10";
    if (/Windows NT 6\.3/.test(ua)) return "Windows 8.1";
    if (/Windows NT 6\.2/.test(ua)) return "Windows 8";
    if (/Windows NT 6\.1/.test(ua)) return "Windows 7";
    if (/Windows NT/.test(ua)) return "Windows";
    if (/Mac OS X/.test(ua)) return "macOS";
    if (/Android/.test(ua)) return "Android";
    if (/iPhone/.test(ua)) return "iOS";
    if (/iPad/.test(ua)) return "iPadOS";
    if (/Linux/.test(ua)) return "Linux";
    return "Unknown";
  })();

  return { browser, os };
}

// Sessions: list active sessions for a user
app.get("/api/v1/auth/sessions", async (req, res) => {
  const userId = (req.query.userId as string) || (req.headers["x-user-id"] as string);
  if (!userId) {
    res.status(400).json({ code: "invalid_query", message: "userId is required" });
    return;
  }

  const page = Math.max(1, Number(req.query.page) || 1);
  const pageSize = Math.min(100, Math.max(1, Number(req.query.pageSize) || 25));
  const sortBy = String(req.query.sortBy ?? "createdAt");
  const sortDir = String(req.query.sortDir ?? "desc").toLowerCase() === "asc" ? "ASC" : "DESC";
  const search = String(req.query.search || "").trim();

  const sortColumns: Record<string, string> = {
    id: "id",
    browser: "user_agent",
    os: "user_agent",
    ipAddress: "ip_address",
    createdAt: "created_at",
    lastActivity: "updated_at",
    expiresAt: "expires_at",
  };

  const orderBy = sortColumns[sortBy] ?? sortColumns.createdAt;
  const conditions = ["user_id = $1"];
  const values: Array<string | number> = [userId];

  if (search) {
    values.push(`%${search}%`, `%${search}%`);
    conditions.push(`(ip_address ILIKE $${values.length - 1} OR user_agent ILIKE $${values.length})`);
  }

  try {
    const countSql = `SELECT COUNT(*) AS total FROM session WHERE ${conditions.join(" AND ")}`;
    const countResult = await dbPool.query(countSql, values);
    const total = Number(countResult.rows[0]?.total ?? 0);

    values.push(pageSize, (page - 1) * pageSize);
    const rows = await dbPool.query(
      `SELECT id, expires_at, ip_address, user_agent, created_at, updated_at
       FROM session
       WHERE ${conditions.join(" AND ")}
       ORDER BY ${orderBy} ${sortDir}
       LIMIT $${values.length - 1}
       OFFSET $${values.length}`,
      values
    );

    const sessions = rows.rows.map((row: any) => {
      const userAgent = row.user_agent ?? null;
      const { browser, os } = parseUserAgent(userAgent);
      return {
        id: row.id,
        ipAddress: row.ip_address,
        userAgent,
        browser,
        os,
        createdAt: row.created_at,
        lastActivity: row.updated_at ?? row.created_at,
        expiresAt: row.expires_at,
      };
    });

    res.json({
      sessions,
      meta: {
        userId,
        total,
        page,
        pageSize,
        sortBy,
        sortDir,
      },
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Failed to query sessions:", e);
    res.status(500).json({ code: "query_failed", message: "Failed to list sessions" });
  }
});

// Passkeys: list registered passkeys for a user
app.get('/api/v1/auth/passkeys', async (req, res) => {
  const userId = (req.query.userId as string) || (req.headers['x-user-id'] as string) || (req as any).user?.id;
  if (!userId) return res.status(400).json({ code: 'invalid_query', message: 'userId is required' });
  try {
    const passkeysModule = await import('./passkeys.js');
    const passkeys = await passkeysModule.listPasskeysForUser(userId);
    res.json({ passkeys });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Failed to query passkeys:', e);
    res.status(500).json({ code: 'query_failed', message: 'Failed to list passkeys' });
  }
});

// Rename a passkey device (user)
app.patch('/api/v1/auth/passkeys/:id', async (req, res) => {
  const deviceId = req.params.id as string;
  const { name } = req.body as { name?: string };
  const userId = (req as any).user?.id || (req.headers['x-user-id'] as string) || (req.query.userId as string);
  if (!deviceId || !name || !userId) return res.status(400).json({ code: 'invalid_body', message: 'device id, name and user context required' });
  try {
    const passkeysModule = await import('./passkeys.js');
    const ok = await passkeysModule.renamePasskey(deviceId, userId, name);
    if (!ok) return res.status(404).json({ code: 'not_found' });
    res.json({ ok: true });
  } catch (e) {
    console.error('Failed to rename passkey:', e);
    res.status(500).json({ code: 'rename_failed' });
  }
});

// Revoke/Delete a passkey (user or admin)
app.delete('/api/v1/auth/passkeys/:id', async (req, res) => {
  const deviceId = req.params.id as string;
  const userId = (req as any).user?.id || (req.headers['x-user-id'] as string) || null;
  const isAdmin = (req as any).user?.roles?.includes('admin') || (req as any).user?.roles?.includes('owner');
  if (!deviceId) return res.status(400).json({ code: 'invalid_body', message: 'device id required' });
  try {
    const passkeysModule = await import('./passkeys.js');
    const ok = await passkeysModule.revokePasskey(deviceId, userId, isAdmin);
    if (!ok) return res.status(404).json({ code: 'not_found' });
    res.json({ ok: true });
  } catch (e) {
    console.error('Failed to revoke passkey:', e);
    res.status(500).json({ code: 'revoke_failed' });
  }
});

// Admin: list all passkeys for an organization
app.get('/api/v1/auth/admin/passkeys', requireRole(['owner','admin']), async (req, res) => {
  const organizationId = req.query.organizationId as string;
  if (!organizationId) return res.status(400).json({ code: 'invalid_query', message: 'organizationId is required' });
  try {
    const passkeysModule = await import('./passkeys.js');
    const passkeys = await passkeysModule.listPasskeysForOrganization(organizationId);
    res.json({ passkeys });
  } catch (e) {
    console.error('Failed to list org passkeys:', e);
    res.status(500).json({ code: 'query_failed' });
  }
});

// Revoke a session by token, id, or delete all sessions for a user
app.delete("/api/v1/auth/sessions", requireRole(["owner", "admin"]), async (req, res) => {
  const { token, id, userId } = req.body as { token?: string; id?: string; userId?: string };
  if (!token && !id && !userId) {
    res.status(400).json({ code: "invalid_body", message: "token, id, or userId is required" });
    return;
  }

  try {
    const redis = await getRedisClient();

    if (token) {
      try {
        await redis.del(`refresh:${token}`);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("Failed to remove refresh token from redis:", e);
      }
      await dbPool.query(`DELETE FROM session WHERE token = $1`, [token]);
      await recordAuditEvent({ userId: userId ?? null, organizationId: null, action: "revoke_session", resourceType: "session", resourceId: null, ipAddress: req.socket.remoteAddress, userAgent: req.headers["user-agent"] });
      res.status(204).send(null);
      return;
    }

    if (id) {
      const result = await dbPool.query(`SELECT token FROM session WHERE id = $1`, [id]);
      const sessionToken = result.rows[0]?.token;
      if (sessionToken) {
        try {
          await redis.del(`refresh:${sessionToken}`);
        } catch (e) {
          // eslint-disable-next-line no-console
          console.error("Failed to remove refresh token from redis:", e);
        }
      }
      await dbPool.query(`DELETE FROM session WHERE id = $1`, [id]);
      await recordAuditEvent({ userId: userId ?? null, organizationId: null, action: "revoke_session", resourceType: "session", resourceId: id, ipAddress: req.socket.remoteAddress, userAgent: req.headers["user-agent"] });
      res.status(204).send(null);
      return;
    }

    if (userId) {
      const sessions = await dbPool.query(`SELECT token FROM session WHERE user_id = $1`, [userId]);
      const tokens = sessions.rows.map((row: any) => row.token).filter(Boolean);
      if (tokens.length) {
        await Promise.all(tokens.map((sessionToken: string) => redis.del(`refresh:${sessionToken}`)));
      }
      await dbPool.query(`DELETE FROM session WHERE user_id = $1`, [userId]);
      await recordAuditEvent({ userId, organizationId: null, action: "revoke_all_sessions", resourceType: "session", resourceId: null, ipAddress: req.socket.remoteAddress, userAgent: req.headers["user-agent"] });
      res.status(204).send(null);
      return;
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Failed to revoke session:", e);
    res.status(500).json({ code: "revoke_failed", message: "Failed to revoke session" });
  }
});

// Invitations: create invite
app.post("/api/v1/auth/invite", rateLimiter(5, 60), requireRole(["owner", "admin"]), async (req, res) => {
  const { organizationId, email, role, expiresAt } = req.body as { organizationId?: string; email?: string; role?: string; expiresAt?: string };
  if (!organizationId || !email) {
    res.status(400).json({ code: "invalid_body", message: "organizationId and email are required" });
    return;
  }

  try {
    const { createInvitation } = await import('./invitations.js');
    const ttlDays = expiresAt ? Math.max(1, Math.round((new Date(expiresAt).getTime() - Date.now()) / (24 * 60 * 60 * 1000))) : undefined;
    const result = await createInvitation({
      organizationId,
      email,
      role,
      inviterId: (req as any).user?.id ?? null,
      ttlDays,
    });
    res.json(result);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Failed to create invitation:", e);
    res.status(500).json({ code: "invite_failed", message: "Failed to create invitation" });
  }
});

// Invitations: reject invite
app.post("/api/v1/auth/invite/reject", requireRole(["owner", "admin"]), async (req, res) => {
  const { invitationId, reason } = req.body as { invitationId?: string; reason?: string };
  if (!invitationId) {
    res.status(400).json({ code: "invalid_body", message: "invitationId is required" });
    return;
  }

  try {
    const { rejectInvitation } = await import('./invitations.js');
    const result = await rejectInvitation({ invitationId, reason, userId: (req as any).user?.id ?? null });
    res.json(result);
  } catch (e) {
    const message = (e as Error).message;
    if (message === 'invite_not_found') return res.status(404).json({ code: 'invite_not_found', message: 'Invitation not found' });
    if (message === 'invite_invalid') return res.status(400).json({ code: 'invite_invalid', message: 'Invitation is not pending' });
    // eslint-disable-next-line no-console
    console.error("Failed to reject invitation:", e);
    res.status(500).json({ code: "reject_failed", message: "Failed to reject invitation" });
  }
});

// Invitations: resend invite
app.post("/api/v1/auth/invite/resend", requireRole(["owner", "admin"]), async (req, res) => {
  const { invitationId, ttlDays } = req.body as { invitationId?: string; ttlDays?: number };
  if (!invitationId) {
    res.status(400).json({ code: "invalid_body", message: "invitationId is required" });
    return;
  }

  try {
    const { resendInvitation } = await import('./invitations.js');
    const result = await resendInvitation({ invitationId, ttlDays, userId: (req as any).user?.id ?? null });
    res.json(result);
  } catch (e) {
    const message = (e as Error).message;
    if (message === 'invite_not_found') return res.status(404).json({ code: 'invite_not_found', message: 'Invitation not found' });
    if (message === 'invite_invalid') return res.status(400).json({ code: 'invite_invalid', message: 'Invitation is not pending' });
    if (message === 'invite_expired') return res.status(400).json({ code: 'invite_expired', message: 'Invitation expired' });
    // eslint-disable-next-line no-console
    console.error("Failed to resend invitation:", e);
    res.status(500).json({ code: "resend_failed", message: "Failed to resend invitation" });
  }
});

// SCIM: trigger sync for organization (admin only)
import { scimSyncScheduledTask } from "./scim.js";
import { seedPermission } from "./neo4j.js";

app.post("/api/v1/auth/scim/sync", requireRole(["owner", "admin"]), async (req, res) => {
  const { organizationId } = req.body as { organizationId?: string };
  try {
    const result = await scimSyncScheduledTask(organizationId);
    res.json(result);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("SCIM sync failed:", e);
    res.status(500).json({ ok: false, message: "scim_error" });
  }
});

// Neo4j: seed permission relationship (admin)
app.post('/api/v1/auth/neo4j/seed', requireRole(['owner','admin']), async (req, res) => {
  const { subjectId, resourceId, action } = req.body as { subjectId?: string; resourceId?: string; action?: string };
  if (!subjectId || !resourceId || !action) return res.status(400).json({ code:'invalid_body' });
  try {
    const r = await seedPermission(subjectId, resourceId, action);
    res.json(r);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Neo4j seed endpoint failed:', e);
    res.status(500).json({ ok:false });
  }
});

// Admin: unlock an account (clear brute-force lock)
app.post("/api/v1/auth/admin/unlock", requireRole(["owner", "admin"]), async (req, res) => {
  const { email } = req.body as { email?: string };
  if (!email) {
    res.status(400).json({ code: "invalid_body", message: "email is required" });
    return;
  }

  try {
    const redis = await getRedisClient();
    await redis.del(`bf:lock:${email}`);
    await redis.del(`bf:fail:${email}`);
    await recordAuditEvent({ userId: null, organizationId: null, action: "admin_unlock", resourceType: "user", resourceId: null, ipAddress: req.socket.remoteAddress, userAgent: req.headers["user-agent"], metadata: { email } });
    res.json({ ok: true });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Failed to unlock account:", e);
    res.status(500).json({ code: "unlock_failed", message: "Failed to unlock account" });
  }
});

// OIDC provider management (store provider config in organization.settings)
app.post("/api/v1/auth/oidc/provider", requireRole(["owner", "admin"]), async (req, res) => {
  const {
    organizationId,
    name,
    issuer,
    clientId,
    clientSecret,
    enabled,
    scopes,
    responseTypes,
    fetchMetadata,
  } = req.body as {
    organizationId?: string;
    name?: string;
    issuer?: string;
    clientId?: string;
    clientSecret?: string;
    enabled?: boolean;
    scopes?: string[];
    responseTypes?: string[];
    fetchMetadata?: boolean;
  };

  if (!organizationId || !name || !issuer || !clientId || !clientSecret) {
    res.status(400).json({ code: "invalid_body", message: "organizationId, name, issuer, clientId, clientSecret are required" });
    return;
  }

  try {
    const provider = await createOidcProvider(organizationId, {
      name,
      issuer,
      clientId,
      clientSecret,
      enabled,
      scopes,
      responseTypes,
    }, { autoFetchMetadata: fetchMetadata });

    await recordAuditEvent({ userId: null, organizationId, action: "create_oidc_provider", resourceType: "oidc_provider", resourceId: provider.id, ipAddress: req.socket.remoteAddress, userAgent: req.headers["user-agent"], metadata: { name, issuer } });
    res.json({ ok: true, provider: sanitizeOidcProvider(provider) });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Failed to register OIDC provider:", e);
    res.status(500).json({ code: "create_failed", message: "Failed to register OIDC provider" });
  }
});

// List OIDC providers for an organization
app.get("/api/v1/auth/oidc/providers", requireRole(["owner", "admin"]), async (req, res) => {
  const organizationId = req.query.organizationId as string;
  const enabledOnly = req.query.enabledOnly === "true";
  if (!organizationId) {
    res.status(400).json({ code: "invalid_query", message: "organizationId is required" });
    return;
  }

  try {
    let providers = await listOidcProviders(organizationId);
    if (enabledOnly) {
      providers = providers.filter((p) => p.enabled);
    }
    res.json({ providers: providers.map((p) => sanitizeOidcProvider(p)) });
  } catch (e) {
    if ((e as Error).message === "org_not_found") {
      return res.status(404).json({ code: "org_not_found" });
    }
    // eslint-disable-next-line no-console
    console.error("Failed to list providers:", e);
    res.status(500).json({ code: "list_failed", message: "Failed to list providers" });
  }
});

// Get a single OIDC provider by id
app.get("/api/v1/auth/oidc/provider/:id", requireRole(["owner", "admin"]), async (req, res) => {
  const providerId = req.params.id as string;
  const organizationId = req.query.organizationId as string;
  if (!providerId || !organizationId) {
    res.status(400).json({ code: "invalid_query", message: "organizationId and provider id are required" });
    return;
  }

  try {
    const provider = await getOidcProvider(organizationId, providerId);
    res.json({ provider: sanitizeOidcProvider(provider) });
  } catch (e) {
    if ((e as Error).message === "provider_not_found") {
      return res.status(404).json({ code: "provider_not_found" });
    }
    if ((e as Error).message === "org_not_found") {
      return res.status(404).json({ code: "org_not_found" });
    }
    // eslint-disable-next-line no-console
    console.error("Failed to read provider:", e);
    res.status(500).json({ code: "get_failed", message: "Failed to read provider" });
  }
});

// Update an OIDC provider by id
app.patch("/api/v1/auth/oidc/provider/:id", requireRole(["owner", "admin"]), async (req, res) => {
  const providerId = req.params.id as string;
  const {
    organizationId,
    name,
    issuer,
    clientId,
    clientSecret,
    enabled,
    scopes,
    responseTypes,
    fetchMetadata,
  } = req.body as {
    organizationId?: string;
    name?: string;
    issuer?: string;
    clientId?: string;
    clientSecret?: string;
    enabled?: boolean;
    scopes?: string[];
    responseTypes?: string[];
    fetchMetadata?: boolean;
  };
  if (!organizationId || !providerId) {
    res.status(400).json({ code: "invalid_body", message: "organizationId and provider id are required" });
    return;
  }

  try {
    const provider = await updateOidcProvider(organizationId, providerId, {
      name,
      issuer,
      clientId,
      clientSecret,
      enabled,
      scopes,
      responseTypes,
      autoFetchMetadata: fetchMetadata,
    });
    await recordAuditEvent({ userId: null, organizationId, action: "update_oidc_provider", resourceType: "oidc_provider", resourceId: providerId, ipAddress: req.socket.remoteAddress, userAgent: req.headers["user-agent"], metadata: { name, issuer } });
    res.json({ ok: true, provider: sanitizeOidcProvider(provider) });
  } catch (e) {
    if ((e as Error).message === "provider_not_found") {
      return res.status(404).json({ code: "provider_not_found" });
    }
    if ((e as Error).message === "org_not_found") {
      return res.status(404).json({ code: "org_not_found" });
    }
    // eslint-disable-next-line no-console
    console.error("Failed to update provider:", e);
    res.status(500).json({ code: "update_failed", message: "Failed to update provider" });
  }
});

// Delete an OIDC provider by id
app.delete("/api/v1/auth/oidc/provider/:id", requireRole(["owner", "admin"]), async (req, res) => {
  const providerId = req.params.id as string;
  const organizationId = req.body.organizationId as string;
  if (!providerId || !organizationId) {
    res.status(400).json({ code: "invalid_body", message: "provider id and organizationId are required" });
    return;
  }
  try {
    await deleteOidcProvider(organizationId, providerId);
    await recordAuditEvent({ userId: null, organizationId, action: "delete_oidc_provider", resourceType: "oidc_provider", resourceId: providerId, ipAddress: req.socket.remoteAddress, userAgent: req.headers["user-agent"] });
    res.json({ ok: true });
  } catch (e) {
    if ((e as Error).message === "org_not_found") {
      return res.status(404).json({ code: "org_not_found" });
    }
    // eslint-disable-next-line no-console
    console.error("Failed to delete provider:", e);
    res.status(500).json({ code: "delete_failed", message: "Failed to delete provider" });
  }
});

// Fetch OIDC metadata for an issuer and store it in provider entry
app.post("/api/v1/auth/oidc/fetch-metadata", requireRole(["owner", "admin"]), async (req, res) => {
  const { organizationId, issuer, providerId } = req.body as { organizationId?: string; issuer?: string; providerId?: string };
  if (!organizationId || !issuer || !providerId) {
    res.status(400).json({ code: "invalid_body", message: "organizationId, issuer, providerId required" });
    return;
  }
  try {
    const metadata = await refreshOidcProviderMetadata(organizationId, providerId, issuer);
    res.json({ ok: true, metadata });
  } catch (e) {
    if ((e as Error).message === "provider_not_found") {
      return res.status(404).json({ code: "provider_not_found" });
    }
    if ((e as Error).message === "org_not_found") {
      return res.status(404).json({ code: "org_not_found" });
    }
    // eslint-disable-next-line no-console
    console.error('Failed to fetch metadata:', e);
    res.status(500).json({ code: 'fetch_error', message: 'Failed to fetch metadata' });
  }
});

// Admin: force JWKS refresh for a provider
app.post('/api/v1/auth/oidc/provider/:id/jwks/refresh', requireRole(['owner','admin']), async (req, res) => {
  const providerId = req.params.id as string;
  const { organizationId } = req.body as { organizationId?: string };
  if (!providerId || !organizationId) return res.status(400).json({ code: 'invalid_body' });
  try {
    const { refreshProviderJwks } = await import('./oidc.js');
    const body = await refreshProviderJwks(organizationId, providerId);
    res.json({ ok: true, jwks: body });
  } catch (e) {
    console.error('Failed to refresh jwks:', e);
    res.status(500).json({ code: 'refresh_failed', message: (e as Error).message });
  }
});

// Provider health/status endpoint (admin)
app.get('/api/v1/auth/oidc/provider/:id/status', requireRole(['owner','admin']), async (req, res) => {
  const providerId = req.params.id as string;
  const organizationId = req.query.organizationId as string;
  if (!providerId || !organizationId) return res.status(400).json({ code: 'invalid_query' });
  try {
    const oidc = await import('./oidc.js');
    const provider = await oidc.getOidcProvider(organizationId, providerId);
    const health = (provider as any).health ?? {};
    res.json({ ok: true, health });
  } catch (e) {
    console.error('Failed to get provider status:', e);
    res.status(404).json({ code: 'provider_not_found' });
  }
});

// RFC 7591 Dynamic Client Registration (tenant-scoped)
app.post('/api/v1/auth/oidc/register', requireRole(['owner','admin']), async (req, res) => {
  const organizationId = req.body.organizationId as string;
  const metadata = req.body.metadata as any;
  if (!organizationId || !metadata) return res.status(400).json({ code: 'invalid_body', message: 'organizationId and metadata required' });
  try {
    const client = await (await import('./oidc.js')).createDynamicClient(organizationId, metadata);
    // RFC response: include client_id, client_secret, registration_access_token, registration_client_uri
    res.status(201).json({
      client_id: client.client_id,
      client_secret: client.client_secret,
      registration_access_token: client.registration_access_token,
      registration_client_uri: client.registration_client_uri,
      client_id_issued_at: client.client_id_issued_at,
      client_secret_expires_at: client.client_secret_expires_at,
      registration_access_token_expires_at: (client as any).registration_access_token_expires_at ?? null,
      ...client.client_metadata
    });
  } catch (e) {
    console.error('Dynamic client registration failed:', e);
    res.status(400).json({ code: 'registration_failed', message: (e as Error).message });
  }
});

// Registration management endpoints: read, update, delete. Authenticated by registration_access_token in Authorization header and tenant-scoped
app.get('/api/v1/auth/oidc/registration/:clientId', async (req, res) => {
  const clientId = req.params.clientId as string;
  const organizationId = req.query.organizationId as string;
  const auth = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  if (!clientId || !organizationId || !auth) return res.status(400).json({ code: 'invalid_request' });
  try {
    const oidc = await import('./oidc.js');
    const ok = await oidc.validateRegistrationAccessToken(organizationId, clientId, auth);
    if (!ok) return res.status(401).json({ code: 'invalid_token' });
    const c = await oidc.getDynamicClient(organizationId, clientId, true);
    const out = { client_id: c.client_id, client_secret: c.client_secret, client_id_issued_at: c.client_id_issued_at, client_secret_expires_at: c.client_secret_expires_at, registration_access_token_expires_at: (c as any).registration_access_token_expires_at ?? null, client_metadata: c.client_metadata };
    res.json(out);
  } catch (e) {
    console.error('Failed to read dynamic client:', e);
    res.status(404).json({ code: 'client_not_found' });
  }
});

app.patch('/api/v1/auth/oidc/registration/:clientId', async (req, res) => {
  const clientId = req.params.clientId as string;
  const organizationId = req.body.organizationId as string;
  const auth = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  const updates = req.body as any;
  if (!clientId || !organizationId || !auth) return res.status(400).json({ code: 'invalid_request' });
  try {
    const oidc = await import('./oidc.js');
    const ok = await oidc.validateRegistrationAccessToken(organizationId, clientId, auth);
    if (!ok) return res.status(401).json({ code: 'invalid_token' });
    const updated = await oidc.updateDynamicClient(organizationId, clientId, updates, true);
    res.json({ client_id: updated.client_id, client_secret: updated.client_secret, client_metadata: updated.client_metadata });
  } catch (e) {
    console.error('Failed to update dynamic client:', e);
    res.status(400).json({ code: 'update_failed', message: (e as Error).message });
  }
});

app.delete('/api/v1/auth/oidc/registration/:clientId', async (req, res) => {
  const clientId = req.params.clientId as string;
  const organizationId = req.body.organizationId as string;
  const auth = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  if (!clientId || !organizationId || !auth) return res.status(400).json({ code: 'invalid_request' });
  try {
    const oidc = await import('./oidc.js');
    const ok = await oidc.validateRegistrationAccessToken(organizationId, clientId, auth);
    if (!ok) return res.status(401).json({ code: 'invalid_token' });
    await oidc.deleteDynamicClient(organizationId, clientId);
    res.status(204).send(null);
  } catch (e) {
    console.error('Failed to delete dynamic client:', e);
    res.status(400).json({ code: 'delete_failed', message: (e as Error).message });
  }
});

// Admin: rotate registration access token for a dynamic client
app.post('/api/v1/auth/oidc/registration/:clientId/rotate', requireRole(['owner','admin']), async (req, res) => {
  const clientId = req.params.clientId as string;
  const { organizationId } = req.body as { organizationId?: string };
  if (!clientId || !organizationId) return res.status(400).json({ code: 'invalid_body' });
  try {
    const oidc = await import('./oidc.js');
    const result = await oidc.rotateRegistrationAccessToken(organizationId, clientId);
    res.json({ ok: true, result });
  } catch (e) {
    console.error('Failed to rotate registration token:', e);
    res.status(500).json({ code: 'rotate_failed', message: (e as Error).message });
  }
});

// Admin: rotate secrets for all organizations
app.post('/api/v1/auth/admin/rotate-secrets', requireRole(['owner','admin']), async (req, res) => {
  try {
    const { rotateSecretsForAllOrganizations } = await import('./crypto.js');
    const r = await rotateSecretsForAllOrganizations();
    await recordAuditEvent({ userId: null, organizationId: null, action: 'rotate_secrets', resourceType: 'organization', resourceId: null, ipAddress: req.socket.remoteAddress, userAgent: req.headers['user-agent'], metadata: r });
    res.json({ ok: true, result: r });
  } catch (e) {
    console.error('Failed to rotate secrets:', e);
    res.status(500).json({ code: 'rotate_failed', message: (e as Error).message });
  }
});

// Admin: rotate keys (key version re-encryption) with options
app.post('/api/v1/auth/admin/keys/rotate', requireRole(['owner','admin']), async (req, res) => {
  const { organizationId, dryRun, force } = req.body as { organizationId?: string; dryRun?: boolean; force?: boolean };
  try {
    const cryptoMod = await import('./crypto.js');
    let result;
    if (organizationId) {
      result = await cryptoMod.rotateSecretsForOrganization(organizationId, { dryRun: !!dryRun });
      await recordAuditEvent({ userId: null, organizationId, action: 'admin_rotate_keys', resourceType: 'organization', resourceId: organizationId, ipAddress: req.socket.remoteAddress, userAgent: req.headers['user-agent'], metadata: { dryRun: !!dryRun, force: !!force, result } });
      return res.json({ ok: true, result });
    }
    result = await cryptoMod.rotateSecretsForAllOrganizations({ dryRun: !!dryRun });
    await recordAuditEvent({ userId: null, organizationId: null, action: 'admin_rotate_keys', resourceType: 'organization', resourceId: null, ipAddress: req.socket.remoteAddress, userAgent: req.headers['user-agent'], metadata: { dryRun: !!dryRun, force: !!force, result } });
    res.json({ ok: true, result });
  } catch (e) {
    console.error('Admin key rotation failed:', e);
    res.status(500).json({ code: 'rotate_failed', message: (e as Error).message });
  }
});

// Invitations: accept invite
app.post("/api/v1/auth/invite/accept", async (req, res) => {
  const { invitationId, userEmail } = req.body as { invitationId?: string; userEmail?: string };
  if (!invitationId || !userEmail) {
    res.status(400).json({ code: "invalid_body", message: "invitationId and userEmail are required" });
    return;
  }

  try {
    const { acceptInvitation } = await import('./invitations.js');
    const userId = (req as any).user?.id ?? null;
    const result = await acceptInvitation({ invitationId, userEmail, userId: userId ?? '' });
    res.json(result);
  } catch (e) {
    const message = (e as Error).message;
    if (message === 'invite_not_found') return res.status(404).json({ code: 'invite_not_found', message: 'Invitation not found' });
    if (message === 'invite_invalid') return res.status(400).json({ code: 'invite_invalid', message: 'Invitation is not pending' });
    if (message === 'invite_expired') return res.status(400).json({ code: 'invite_expired', message: 'Invitation expired' });
    if (message === 'invite_mismatch') return res.status(400).json({ code: 'invite_mismatch', message: 'Invitation email does not match' });
    if (message === 'user_not_found') return res.status(404).json({ code: 'user_not_found', message: 'User must register first' });
    if (message === 'user_mismatch') return res.status(400).json({ code: 'user_mismatch', message: 'Logged-in user does not match invitation email' });
    // eslint-disable-next-line no-console
    console.error("Failed to accept invitation:", e);
    res.status(500).json({ code: "accept_failed", message: "Failed to accept invitation" });
  }
});

// BetterAuth owns its endpoints (SSO callbacks, passkey challenge, session state)
// mounted at /api/v1/auth/*. Register this last so the custom endpoints above
// remain reachable and are not swallowed by the wildcard handler.
app.all("/api/v1/auth/*", toNodeHandler(auth));

// Boot-up logic
initDatabase()
  .then(() => {
    app.listen(Number(config.port), async () => {
      // eslint-disable-next-line no-console
      console.log(
        JSON.stringify({
          level: "INFO",
          msg: "Auth service listening",
          port: config.port,
        })
      );
      console.log("Registered Routes:");

(app as any)._router.stack.forEach((r: any) => {
  if (r.route) {
    console.log(
      Object.keys(r.route.methods),
      r.route.path
    );
  }
});
      try {
        // Start background SCIM worker (no-op in tests)
        const scimWorker = await import('./scimWorker.js');
        scimWorker.startScimWorker?.();
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error('Failed to start SCIM worker:', e);
      }
      try {
        const jwks = await import('./jwksCache.js');
        jwks.startBackgroundRefresh?.();
      } catch (e) {
        console.error('Failed to start JWKS background refresher:', e);
      }
    });
  })
  .catch((err) => {
    // eslint-disable-next-line no-console
    console.error(
      "Critical: Failed to start auth service due to database initialization failure",
      err
    );
    process.exit(1);
  });
