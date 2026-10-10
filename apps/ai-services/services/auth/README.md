# services/auth

This service provides enterprise authentication features for AI-RxOS.

Features implemented:
- BetterAuth integration (email/password, social providers)
- OAuth2/OIDC (via BetterAuth socialProviders)
- SSO plugin + SCIM provisioning plugin integration
- MFA and Passkeys via BetterAuth plugins
- RBAC helper middleware
- ABAC evaluator with optional Neo4j consultation
- JWT access tokens and rotated refresh tokens stored in Redis
- Session management (DB session rows) with endpoints to list/revoke
- Tenant isolation via Postgres RLS and optional Neo4j-scoped checks
- Invitations flow and audit logging
- Rate limiting and brute-force protection (Redis)

Runs on port **8081**. See `architecture/02-microservices.md` §1.1.

Local Docker-backed verification path:

```bash
docker compose up -d postgres redis
cd services/auth
pnpm install
pnpm exec vitest run --reporter=basic
```

Verified runtime environment for Windows local startup:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:DATABASE_URL='postgresql://ai_rxos:changeme@127.0.0.1:15432/ai_rxos'
$env:REDIS_URL='redis://localhost:6379'
$env:PORT='8081'
$env:BETTER_AUTH_SECRET='mysupersecretkey12345678901234567890'
$env:JWT_SECRET='myjwtsecret12345678901234567890'
$env:AUDIT_LOG_HMAC_SECRET='audit-hmac-secret-for-local-dev'
$env:KEY_MANAGEMENT_PROVIDER='env'
$env:ACTIVE_MASTER_KEY='v1'
$env:MASTER_KEY_V1='<replace-with-a-real-32-byte-base64-key>'
pnpm exec tsx src/index.ts
```

OIDC dynamic client registration note:
- `KEY_MANAGEMENT_PROVIDER=env` and a valid `MASTER_KEY_V1` are required for the `/oidc/register` route to return `201`.
- `ACTIVE_MASTER_KEY=v1` selects the active key version when the env registry is used.

Docker Compose note:
- Postgres is exposed on host port `15432` for local Windows verification.
- The auth service is containerized via `services/auth/Dockerfile` and mapped to `http://localhost:8081`.
- The service now serves the admin UIs at `/admin/sessions` and `/admin/passkeys`.

Testing:

```bash
cd services/auth
pnpm exec vitest run --reporter=basic
```
